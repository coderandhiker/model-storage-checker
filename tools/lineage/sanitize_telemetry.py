#!/usr/bin/env python3
"""Build a deterministic, publishable lineage evidence package.

The source directory is treated as read-only. Raw message content is never
printed by this tool; confidential fields are replaced structurally and each
replacement is recorded by category, path, and SHA-256.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = 1
REDACTION_PREFIX = "[REDACTED:"
REMOVAL_PREFIX = "[REMOVED:"

SYSTEM_FIELD_NAMES = {
    "developer_instructions",
    "developer_message",
    "developer_prompt",
    "gen_ai_system_instructions",
    "system_instructions",
    "system_message",
    "system_prompt",
}
TOOL_DEFINITION_FIELD_NAMES = {
    "available_functions",
    "available_tools",
    "function_catalog",
    "function_definitions",
    "function_schemas",
    "gen_ai_tool_definitions",
    "mcp_instructions",
    "tool_catalog",
    "tool_definitions",
    "tool_schemas",
}
CONTEXT_CATALOG_FIELD_NAMES = {
    "github_copilot_context_custom_agent_names",
    "github_copilot_context_mcp_server_names",
    "github_copilot_context_skills",
}
SANDBOX_POLICY_FIELD_NAMES = {
    "github_copilot_sandbox_policy_denied_paths",
    "github_copilot_sandbox_policy_readonly_paths",
    "github_copilot_sandbox_policy_readwrite_paths",
}
SENSITIVE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "cookie",
    "credentials",
    "docker_auth",
    "password",
    "passwd",
    "private_key",
    "proxy_authorization",
    "refresh_token",
    "secret",
    "secret_key",
    "set_cookie",
    "trampoline_token",
}
INTERNAL_AUDIT_FIELDS = {
    "cwd",
    "environment_variable_names",
    "sanitized_argv",
    "secret_environment_variable_names",
    "worktree",
}
PATH_FIELD_SUFFIXES = (
    "_path",
    "_paths",
    "_log",
    "_root",
    "directory",
    "worktree",
)
PATH_FIELD_NAMES = {"directory", "log", "path", "worktree"}
JSON_SUFFIXES = {".json", ".jsonl"}


@dataclass(frozen=True)
class SecretPattern:
    category: str
    regex: re.Pattern[str]


SECRET_PATTERNS = (
    SecretPattern(
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
        ),
    ),
    SecretPattern(
        "github_token",
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|"
            r"github_pat_[A-Za-z0-9_]{40,})\b"
        ),
    ),
    SecretPattern(
        "openai_key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    SecretPattern(
        "anthropic_key",
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    ),
    SecretPattern(
        "aws_access_key_id",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    SecretPattern(
        "aws_secret_access_key",
        re.compile(
            r"(?i)\baws_secret_access_key\s*[:=]\s*"
            r"[\"']?[A-Za-z0-9/+=]{40}"
        ),
    ),
    SecretPattern(
        "aws_session_token",
        re.compile(
            r"(?i)\baws_session_token\s*[:=]\s*"
            r"[\"']?[A-Za-z0-9/+=]{40,}"
        ),
    ),
    SecretPattern(
        "npm_token",
        re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"),
    ),
    SecretPattern(
        "slack_token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
    SecretPattern(
        "jwt",
        re.compile(
            r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{5,}\."
            r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{10,}"
            r"(?![A-Za-z0-9_-])"
        ),
    ),
    SecretPattern(
        "authorization_header",
        re.compile(
            r"(?im)\b(?:proxy-)?authorization\s*:\s*"
            r"(?:bearer|basic|token)\s+[^\s,;]+"
        ),
    ),
    SecretPattern(
        "cookie_header",
        re.compile(r"(?im)\b(?:set-cookie|cookie)\s*:\s*[^\r\n]+"),
    ),
    SecretPattern(
        "credential_url",
        re.compile(r"(?i)\bhttps?://[^/\s:@]+:[^/\s@]+@[^\s]+"),
    ),
    SecretPattern(
        "docker_auth_value",
        re.compile(r'(?i)"auth"\s*:\s*"[A-Za-z0-9+/=]{12,}"'),
    ),
    SecretPattern(
        "trampoline_token",
        re.compile(
            r"(?i)\btrampoline[_-]?token\s*[:=]\s*"
            r"[\"']?[A-Za-z0-9._~+/-]{12,}"
        ),
    ),
    SecretPattern(
        "named_secret_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
            r"client[_-]?secret|password|passwd)\s*[:=]\s*"
            r"[\"']?[A-Za-z0-9._~+/-]{12,}"
        ),
    ),
    SecretPattern(
        "credential_environment_assignment",
        re.compile(
            r"(?i)\b(?:github_token|openai_api_key|anthropic_api_key|npm_token|"
            r"slack_token|docker_auth_config)\s*[:=]\s*"
            r"[\"']?[^\s\"']{12,}"
        ),
    ),
)


def canonical_bytes(value: Any) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def json_path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key)}]"


def marker(kind: str, category: str, digest: str) -> str:
    return f"[{kind}:{category.upper()}:{digest[:12]}]"


class RedactionRecorder:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(
        self,
        *,
        category: str,
        source_file: str,
        path: str,
        key: str,
        original: Any,
        kind: str = "REDACTED",
        replacement: str | None = None,
    ) -> str:
        digest = sha256_value(original)
        replacement_value = replacement or marker(kind, category, digest)
        self.entries.append(
            {
                "category": category,
                "json_path": path,
                "key": key,
                "original_sha256": digest,
                "replacement_marker": replacement_value,
                "source_file": source_file,
            }
        )
        return replacement_value

    def report(self) -> dict[str, Any]:
        by_category = collections.Counter(
            entry["category"] for entry in self.entries
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "summary": {
                "total_redactions": len(self.entries),
                "by_category": dict(sorted(by_category.items())),
            },
            "entries": sorted(
                self.entries,
                key=lambda item: (
                    item["source_file"],
                    item["json_path"],
                    item["category"],
                    item["original_sha256"],
                ),
            ),
        }


def iter_secret_matches(text: str) -> Iterator[tuple[str, re.Match[str]]]:
    for pattern in SECRET_PATTERNS:
        for match in pattern.regex.finditer(text):
            yield pattern.category, match


def redact_secrets(
    text: str,
    *,
    source_file: str,
    path: str,
    key: str,
    recorder: RedactionRecorder,
) -> str:
    updated = text
    for pattern in SECRET_PATTERNS:
        cursor = 0
        pieces: list[str] = []
        changed = False
        for match in pattern.regex.finditer(updated):
            changed = True
            pieces.append(updated[cursor : match.start()])
            pieces.append(
                recorder.record(
                    category=pattern.category,
                    source_file=source_file,
                    path=path,
                    key=key,
                    original=match.group(0),
                )
            )
            cursor = match.end()
        if changed:
            pieces.append(updated[cursor:])
            updated = "".join(pieces)
    return updated


def record_nested_secrets(
    value: Any,
    *,
    source_file: str,
    path: str,
    recorder: RedactionRecorder,
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            record_nested_secrets(
                child,
                source_file=source_file,
                path=json_path(path, key),
                recorder=recorder,
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            record_nested_secrets(
                child,
                source_file=source_file,
                path=json_path(path, index),
                recorder=recorder,
            )
    elif isinstance(value, str):
        for category, match in iter_secret_matches(value):
            recorder.record(
                category=category,
                source_file=source_file,
                path=path,
                key=path.rsplit(".", 1)[-1],
                original=match.group(0),
            )


def confidential_field_category(
    *,
    key: str,
    ancestors: tuple[str, ...],
    message_role: str | None,
) -> str | None:
    normalized = normalized_name(key)
    ancestor_names = tuple(normalized_name(item) for item in ancestors)
    if normalized in SYSTEM_FIELD_NAMES:
        return "system_instructions"
    if normalized in TOOL_DEFINITION_FIELD_NAMES:
        return "tool_definitions"
    if normalized in CONTEXT_CATALOG_FIELD_NAMES:
        return "available_context_catalog"
    if normalized in SANDBOX_POLICY_FIELD_NAMES:
        return "sandbox_policy"
    if normalized == "gen_ai_tool_description":
        return "tool_definition_description"
    if normalized in SENSITIVE_FIELD_NAMES:
        return "credential_field"
    public_message = message_role in {"assistant", "tool", "user"}
    request_context = any(
        name
        in {
            "body",
            "model_request",
            "payload",
            "request",
            "request_body",
        }
        or name.endswith("_request")
        for name in ancestor_names
    )
    if not public_message and request_context:
        if normalized in {"functions", "tools"}:
            return "tool_definitions"
        if normalized in {"instructions", "system", "developer"}:
            return "system_instructions"
    return None


def sanitize_value(
    value: Any,
    *,
    source_file: str,
    path: str,
    ancestors: tuple[str, ...],
    message_role: str | None,
    recorder: RedactionRecorder,
) -> Any:
    if isinstance(value, dict):
        role_value = value.get("role")
        role = (
            role_value.casefold()
            if isinstance(role_value, str)
            else message_role
        )
        if role in {"developer", "system"}:
            record_nested_secrets(
                value,
                source_file=source_file,
                path=path,
                recorder=recorder,
            )
            category = f"{role}_message"
            replacement = recorder.record(
                category=category,
                source_file=source_file,
                path=path,
                key="<message>",
                original=value,
            )
            return {"role": role, "content": replacement}

        output: dict[str, Any] = {}
        for key, child in value.items():
            child_path = json_path(path, key)
            category = confidential_field_category(
                key=key,
                ancestors=ancestors,
                message_role=role,
            )
            if category is not None:
                record_nested_secrets(
                    child,
                    source_file=source_file,
                    path=child_path,
                    recorder=recorder,
                )
                output[key] = recorder.record(
                    category=category,
                    source_file=source_file,
                    path=child_path,
                    key=key,
                    original=child,
                )
                continue
            output[key] = sanitize_value(
                child,
                source_file=source_file,
                path=child_path,
                ancestors=(*ancestors, key),
                message_role=role,
                recorder=recorder,
            )
        return output

    if isinstance(value, list):
        return [
            sanitize_value(
                child,
                source_file=source_file,
                path=json_path(path, index),
                ancestors=ancestors,
                message_role=message_role,
                recorder=recorder,
            )
            for index, child in enumerate(value)
        ]

    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                nested = json.loads(value)
            except json.JSONDecodeError:
                pass
            else:
                sanitized_nested = sanitize_value(
                    nested,
                    source_file=source_file,
                    path=f"{path}::<json>",
                    ancestors=ancestors,
                    message_role=message_role,
                    recorder=recorder,
                )
                if sanitized_nested == nested:
                    return redact_secrets(
                        value,
                        source_file=source_file,
                        path=path,
                        key=path.rsplit(".", 1)[-1],
                        recorder=recorder,
                    )
                return json.dumps(
                    sanitized_nested,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
        return redact_secrets(
            value,
            source_file=source_file,
            path=path,
            key=path.rsplit(".", 1)[-1],
            recorder=recorder,
        )
    return value


def sanitize_document(
    value: Any,
    *,
    source_file: str,
    recorder: RedactionRecorder,
) -> Any:
    return sanitize_value(
        value,
        source_file=source_file,
        path="$",
        ancestors=(),
        message_role=None,
        recorder=recorder,
    )


def relative_to_source(path_value: str, source_root: Path) -> str | None:
    candidate = Path(path_value)
    if not candidate.is_absolute():
        return Path(path_value).as_posix()
    try:
        return candidate.relative_to(source_root).as_posix()
    except ValueError:
        return None


def published_relative_path(relative: str) -> str | None:
    normalized = Path(relative).as_posix()
    if normalized == "raw":
        return "otel"
    if normalized.startswith("raw/"):
        return f"otel/{normalized.removeprefix('raw/')}"
    if normalized == "logs" or normalized.startswith("logs/"):
        return None
    if normalized == "transcripts" or normalized.startswith("transcripts/"):
        return None
    return normalized


def normalize_artifact_paths(
    value: Any,
    *,
    source_file: str,
    source_root: Path,
    recorder: RedactionRecorder,
    path: str = "$",
) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            child_path = json_path(path, key)
            if key in INTERNAL_AUDIT_FIELDS:
                recorder.record(
                    category="internal_launcher_runtime",
                    source_file=source_file,
                    path=child_path,
                    key=key,
                    original=child,
                    kind="REMOVED",
                )
                continue
            output[key] = normalize_artifact_paths(
                child,
                source_file=source_file,
                source_root=source_root,
                recorder=recorder,
                path=child_path,
            )
        return output
    if isinstance(value, list):
        return [
            normalize_artifact_paths(
                child,
                source_file=source_file,
                source_root=source_root,
                recorder=recorder,
                path=json_path(path, index),
            )
            for index, child in enumerate(value)
        ]
    if isinstance(value, str):
        key = path.rsplit(".", 1)[-1].strip('[]"')
        artifact_path = ".artifact_paths." in path
        if value.startswith("/") and (
            artifact_path
            or key in PATH_FIELD_NAMES
            or key.endswith(PATH_FIELD_SUFFIXES)
        ):
            relative = relative_to_source(value, source_root)
            if relative is not None:
                published = published_relative_path(relative)
                if published is not None:
                    return published
                return recorder.record(
                    category="unpublished_artifact_path",
                    source_file=source_file,
                    path=path,
                    key=key,
                    original=value,
                    kind="REMOVED",
                )
            return recorder.record(
                category="local_absolute_path",
                source_file=source_file,
                path=path,
                key=key,
                original=value,
                kind="REMOVED",
            )
    return value


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            handle.write("\n")


def reset_output(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for directory in ("otel", "prompts", "usage", "validation"):
        candidate = output_root / directory
        if candidate.exists():
            shutil.rmtree(candidate)
    for filename in (
        "artifact-integrity.json",
        "driver-audit.jsonl",
        "manifest.json",
        "redaction-report.json",
    ):
        candidate = output_root / filename
        if candidate.exists():
            candidate.unlink()


def iter_jsonl(path: Path) -> Iterator[Any]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSONL: {error}"
                ) from error


def prompt_secret_findings(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return sorted({category for category, _ in iter_secret_matches(text)})


def copy_prompts(
    source_root: Path,
    output_root: Path,
) -> list[dict[str, Any]]:
    prompt_dir = source_root / "prompts"
    destination = output_root / "prompts"
    destination.mkdir(parents=True, exist_ok=True)
    prompt_records: list[dict[str, Any]] = []
    for source in sorted(prompt_dir.glob("*.md")):
        findings = prompt_secret_findings(source)
        if findings:
            raise ValueError(
                f"Explicit prompt failed secret scan: {source.name}: "
                f"{', '.join(findings)}"
            )
        target = destination / source.name
        shutil.copyfile(source, target)
        source_bytes = source.read_bytes()
        target_bytes = target.read_bytes()
        if source_bytes != target_bytes:
            raise ValueError(f"Prompt copy was not byte-exact: {source.name}")
        prompt_records.append(
            {
                "path": target.relative_to(output_root).as_posix(),
                "sha256": hashlib.sha256(target_bytes).hexdigest(),
                "size_bytes": len(target_bytes),
            }
        )
    return prompt_records


def clean_verification(
    value: Any,
    *,
    source_file: str,
    path: str,
    recorder: RedactionRecorder,
) -> Any:
    if not isinstance(value, dict):
        return value
    output = dict(value)
    if output.get("passed") is True:
        for key in ("error", "reason", "recovery"):
            if key in output:
                recorder.record(
                    category="stale_intermediate_error",
                    source_file=source_file,
                    path=json_path(path, key),
                    key=key,
                    original=output[key],
                    kind="REMOVED",
                )
                output.pop(key)
    return output


def public_path(value: Any, source_root: Path) -> Any:
    if isinstance(value, str):
        relative = relative_to_source(value, source_root)
        if relative is not None:
            return published_relative_path(relative)
        return value
    return value


def public_verification(
    value: Any,
    *,
    source_root: Path,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed_keys = (
        "actual_branch",
        "artifacts_nonempty",
        "base_sha",
        "coauthor_trailer_exact",
        "commit_count_above_base",
        "commit_sha",
        "full_content_evidence",
        "otel_records",
        "otel_spans",
        "passed",
        "pre_amend_commit_sha",
        "process_exit_zero",
        "python_version",
        "session_trailer_exact",
        "subject_exact",
        "tests_passed",
        "worktree_clean",
    )
    output = {key: value[key] for key in allowed_keys if key in value}
    if isinstance(value.get("otel_files"), list):
        output["otel_files"] = []
        for item in value["otel_files"]:
            if not isinstance(item, dict):
                continue
            relative = public_path(item.get("path"), source_root)
            output["otel_files"].append(
                {
                    **{
                        key: item.get(key)
                        for key in ("invocation", "records", "spans")
                        if key in item
                    },
                    "path": relative,
                }
            )
    return output


def normalized_command_argv(
    argv: Any,
    *,
    source_file: str,
    path: str,
    source_root: Path,
    recorder: RedactionRecorder,
) -> list[Any]:
    if not isinstance(argv, list):
        return []
    output: list[Any] = []
    for index, argument in enumerate(argv):
        if not isinstance(argument, str) or not argument.startswith("/"):
            output.append(argument)
            continue
        relative = relative_to_source(argument, source_root)
        if relative is not None:
            replacement = published_relative_path(relative)
        else:
            replacement = Path(argument).name
        if replacement is None:
            replacement = Path(argument).name
        recorder.record(
            category="internal_launcher_runtime",
            source_file=source_file,
            path=json_path(path, index),
            key=str(index),
            original=argument,
            kind="NORMALIZED",
            replacement=replacement,
        )
        output.append(replacement)
    return output


def normalize_usage_paths(
    value: Any,
    *,
    source_file: str,
    source_root: Path,
    repository_roots: Iterable[Path],
    recorder: RedactionRecorder,
    path: str = "$",
) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_usage_paths(
                child,
                source_file=source_file,
                source_root=source_root,
                repository_roots=repository_roots,
                recorder=recorder,
                path=json_path(path, key),
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            normalize_usage_paths(
                child,
                source_file=source_file,
                source_root=source_root,
                repository_roots=repository_roots,
                recorder=recorder,
                path=json_path(path, index),
            )
            for index, child in enumerate(value)
        ]
    if (
        isinstance(value, str)
        and value.startswith("/")
        and ".codeChanges.filesModified[" in path
    ):
        candidate = Path(value)
        replacement: str | None = None
        for root in sorted(repository_roots, key=lambda item: len(str(item)), reverse=True):
            try:
                replacement = candidate.relative_to(root).as_posix()
                break
            except ValueError:
                continue
        if replacement is None:
            relative = relative_to_source(value, source_root)
            if relative is not None:
                replacement = published_relative_path(relative)
        if replacement is not None:
            recorder.record(
                category="local_absolute_path",
                source_file=source_file,
                path=path,
                key="filesModified",
                original=value,
                kind="NORMALIZED",
                replacement=replacement,
            )
            return replacement
    return value


def normalize_manifest(
    raw: dict[str, Any],
    *,
    source_root: Path,
    package_branch: str | None,
    package_commit: str | None,
    publication_metadata: dict[str, Any],
    recorder: RedactionRecorder,
) -> dict[str, Any]:
    source_file = "run-manifest.json"
    for key in ("run_directory", "worktree_root", "launcher"):
        if key in raw:
            recorder.record(
                category=(
                    "internal_launcher_runtime"
                    if key == "launcher"
                    else "local_absolute_path"
                ),
                source_file=source_file,
                path=json_path("$", key),
                key=key,
                original=raw[key],
                kind="REMOVED",
            )

    smoke_attempts = (
        raw.get("preflight_evidence", {}).get("nested_smoke_attempts", [])
    )
    smoke_results = collections.Counter(
        attempt.get("result", "unknown")
        for attempt in smoke_attempts
        if isinstance(attempt, dict)
    )
    smoke_summary = {
        "attempt_count": len(smoke_attempts),
        "by_result": dict(sorted(smoke_results.items())),
        "conclusion": (
            "Logical parent/child linkage is captured by session IDs and driver "
            "audit records. The host launched each process attempt; no W3C trace "
            "context or operating-system child-process nesting is claimed."
        ),
    }

    def artifact_paths(record: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
        return {
            key.removesuffix("_path"): public_path(record[key], source_root)
            for key in keys
            if record.get(key) is not None
        }

    parent_raw = raw.get("parent", {})
    parent = {
        "role": parent_raw.get("role"),
        "session_id": parent_raw.get("session_id"),
        "status": parent_raw.get("status"),
        "started_at": parent_raw.get("started_at"),
        "ended_at": parent_raw.get("ended_at"),
        "exit_code": parent_raw.get("exit_code"),
        "evidence": artifact_paths(
            parent_raw,
            (
                "prompt_path",
                "delegation_plan_path",
                "telemetry_path",
                "usage_path",
            ),
        ),
        "verification": public_verification(
            parent_raw.get("verification", {}),
            source_root=source_root,
        ),
    }

    children: list[dict[str, Any]] = []
    for index, child_raw in enumerate(raw.get("children", [])):
        verification = clean_verification(
            child_raw.get("verification", {}),
            source_file=source_file,
            path=f"$.children[{index}].verification",
            recorder=recorder,
        )
        if verification.get("passed") is True and "error" in child_raw:
            recorder.record(
                category="stale_intermediate_error",
                source_file=source_file,
                path=f"$.children[{index}].error",
                key="error",
                original=child_raw["error"],
                kind="REMOVED",
            )
        if "worktree" in child_raw:
            recorder.record(
                category="local_absolute_path",
                source_file=source_file,
                path=f"$.children[{index}].worktree",
                key="worktree",
                original=child_raw["worktree"],
                kind="REMOVED",
            )
        process_attempts = []
        for attempt in child_raw.get("process_invocations", []):
            process_attempts.append(
                {
                    "kind": attempt.get("kind"),
                    "exit_code": attempt.get("exit_code"),
                    "evidence": artifact_paths(
                        attempt,
                        ("telemetry_path", "usage_path"),
                    ),
                }
            )
        tests = []
        raw_tests = child_raw.get("tests", child_raw.get("commands", []))
        for test_index, test in enumerate(raw_tests):
            if test.get("log") is not None:
                recorder.record(
                    category="unpublished_artifact_path",
                    source_file=source_file,
                    path=f"$.children[{index}].tests[{test_index}].log",
                    key="log",
                    original=test["log"],
                    kind="REMOVED",
                )
            tests.append(
                {
                    "argv": normalized_command_argv(
                        test.get("argv", []),
                        source_file=source_file,
                        path=f"$.children[{index}].tests[{test_index}].argv",
                        source_root=source_root,
                        recorder=recorder,
                    ),
                    "exit_code": test.get("exit_code"),
                }
            )
        children.append(
            {
                "layer": child_raw.get("layer"),
                "layer_name": child_raw.get("layer_name"),
                "session_id": child_raw.get("session_id"),
                "parent_session_id": child_raw.get("parent_session_id"),
                "branch": child_raw.get("branch"),
                "base_branch": child_raw.get("base_branch"),
                "commit_subject": child_raw.get("commit_subject"),
                "status": child_raw.get("status"),
                "started_at": child_raw.get("started_at"),
                "ended_at": child_raw.get("ended_at"),
                "commit_sha": child_raw.get("commit_sha"),
                "parent_sha": child_raw.get("parent_sha"),
                "tree_sha": child_raw.get("tree_sha"),
                "process_exit_code": child_raw.get("process_exit_code"),
                "evidence": artifact_paths(
                    child_raw,
                    ("prompt_path", "telemetry_path", "usage_path"),
                ),
                "tests": tests,
                "process_attempts": process_attempts,
                "verification": public_verification(
                    verification,
                    source_root=source_root,
                ),
                "pull_request": publication_metadata.get(
                    "pull_requests", {}
                ).get(child_raw.get("branch")),
            }
        )

    validation = raw.get("validation", {})
    captures = []
    for capture in validation.get("captures", []):
        captures.append(
            {
                **{
                    key: capture.get(key)
                    for key in (
                        "name",
                        "session_id",
                        "otel_records",
                        "spans",
                        "output_records",
                        "resource_attributes_match",
                        "full_content_evidence",
                    )
                },
                "telemetry_path": public_path(
                    capture.get("telemetry_path"), source_root
                ),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "package": {
            "name": raw.get("poc", {}).get("name"),
            "run": raw.get("poc", {}).get("run"),
            "source_directory_name": source_root.name,
            "package_branch": package_branch,
            "package_commit": package_commit,
        },
        "created_at": raw.get("created_at"),
        "status": raw.get("status"),
        "repository": {
            "full_name": raw.get("repository", {}).get("full_name"),
            "origin_main_sha": raw.get("repository", {}).get("origin_main_sha"),
            "production_dependencies": raw.get("repository", {}).get(
                "production_dependencies"
            ),
        },
        "host_app_session_id": raw.get("host_app_session_id"),
        "orchestration": {
            **raw.get("orchestration", {}),
            "standards_note": (
                "This is host-driven logical lineage, not W3C distributed "
                "trace propagation."
            ),
            "nested_smoke": smoke_summary,
        },
        "parent": parent,
        "children": children,
        "capture_summary": {
            "logical_sessions": validation.get("logical_sessions"),
            "process_capture_files": validation.get("process_capture_files"),
            "otel_records": validation.get("otel_records"),
            "otel_spans": validation.get("otel_spans"),
            "output_json_records": validation.get("output_json_records"),
            "driver_audit_records": validation.get("driver_audit_records"),
            "captures": captures,
        },
        "test_summary": {
            key: validation.get("final_tests", {}).get(key)
            for key in ("python", "tests_run", "passed")
            if key in validation.get("final_tests", {})
        },
        "publication": {
            "metadata_path": (
                "publication-metadata.json"
                if publication_metadata.get("pull_requests")
                or publication_metadata.get("release") is not None
                else None
            ),
            "pull_requests": publication_metadata.get("pull_requests", {}),
            "pull_request": publication_metadata.get(
                "pull_requests", {}
            ).get(package_branch),
            "release": publication_metadata.get("release"),
        },
        "pull_request": publication_metadata.get(
            "pull_requests", {}
        ).get(package_branch),
        "release": publication_metadata.get("release"),
    }


def normalize_base_branch(value: str) -> str:
    return value.removeprefix("origin/")


def validate_publication_metadata(
    value: Any,
    *,
    raw_manifest: dict[str, Any],
    package_branch: str | None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Publication metadata must be a JSON object")
    pull_requests = value.get("pull_requests")
    if not isinstance(pull_requests, dict):
        raise ValueError("Publication metadata requires a pull_requests object")
    repository = raw_manifest.get("repository", {}).get("full_name")
    children = {
        child.get("branch"): child
        for child in raw_manifest.get("children", [])
        if isinstance(child, dict) and isinstance(child.get("branch"), str)
    }
    missing = sorted(set(children) - set(pull_requests))
    extra = sorted(
        set(pull_requests)
        - set(children)
        - ({package_branch} if package_branch is not None else set())
    )
    if missing:
        raise ValueError(
            "Publication metadata is missing child branches: "
            + ", ".join(missing)
        )
    if extra:
        raise ValueError(
            "Publication metadata has unknown branches: " + ", ".join(extra)
        )

    normalized_pull_requests: dict[str, Any] = {}
    required = {"number", "url", "state", "draft", "base", "head_sha"}
    for branch, metadata in sorted(pull_requests.items()):
        if not isinstance(metadata, dict):
            raise ValueError(f"PR metadata for {branch} must be an object")
        absent = sorted(required - set(metadata))
        if absent:
            raise ValueError(
                f"PR metadata for {branch} is missing: {', '.join(absent)}"
            )
        number = metadata["number"]
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ValueError(f"PR number for {branch} must be a positive integer")
        expected_url = f"https://github.com/{repository}/pull/{number}"
        if metadata["url"] != expected_url:
            raise ValueError(
                f"PR URL for {branch} must be {expected_url}"
            )
        if metadata["state"] not in {"closed", "merged", "open"}:
            raise ValueError(f"PR state for {branch} is unsupported")
        if not isinstance(metadata["draft"], bool):
            raise ValueError(f"PR draft flag for {branch} must be boolean")
        if not isinstance(metadata["base"], str) or not metadata["base"]:
            raise ValueError(f"PR base for {branch} must be non-empty")
        if not re.fullmatch(r"[0-9a-f]{40}", str(metadata["head_sha"])):
            raise ValueError(f"PR head SHA for {branch} must be 40 hex characters")

        child = children.get(branch)
        if child is not None:
            if metadata["head_sha"] != child.get("commit_sha"):
                raise ValueError(
                    f"PR head SHA for {branch} does not match the verified commit"
                )
            expected_base = normalize_base_branch(str(child.get("base_branch", "")))
            if normalize_base_branch(metadata["base"]) != expected_base:
                raise ValueError(
                    f"PR base for {branch} does not match {expected_base}"
                )
        normalized_pull_requests[branch] = {
            key: metadata[key]
            for key in ("number", "url", "state", "draft", "base", "head_sha")
        }

    release = value.get("release")
    if release is not None and not isinstance(release, dict):
        raise ValueError("Publication release metadata must be null or an object")
    return {
        "schema_version": SCHEMA_VERSION,
        "pull_requests": normalized_pull_requests,
        "release": release,
    }


def hash_collection(values: Iterable[str]) -> dict[str, Any]:
    digests = sorted(hashlib.sha256(value.encode("utf-8")).hexdigest() for value in values)
    aggregate = hashlib.sha256("\n".join(digests).encode("ascii")).hexdigest()
    return {"count": len(digests), "combined_sha256": aggregate}


def collect_preserved_evidence(value: Any) -> dict[str, list[str]]:
    collected: dict[str, list[str]] = collections.defaultdict(list)

    def add_messages(raw_value: Any, expected_role: str) -> None:
        if not isinstance(raw_value, str):
            return
        try:
            messages = json.loads(raw_value)
        except json.JSONDecodeError:
            return
        if not isinstance(messages, list):
            return
        for message in messages:
            if (
                isinstance(message, dict)
                and str(message.get("role", "")).casefold() == expected_role
            ):
                collected[f"{expected_role}_messages"].append(
                    json.dumps(
                        message,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                )

    def walk(current: Any) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                normalized = normalized_name(key)
                if normalized == "gen_ai_tool_call_arguments":
                    collected["tool_call_arguments"].append(str(child))
                elif normalized == "gen_ai_tool_call_result":
                    collected["tool_call_results"].append(str(child))
                elif normalized == "gen_ai_input_messages":
                    add_messages(child, "user")
                    add_messages(child, "tool")
                elif normalized == "gen_ai_output_messages":
                    add_messages(child, "assistant")
                elif normalized in SYSTEM_FIELD_NAMES:
                    collected["system_fields"].append(str(child))
                elif normalized in TOOL_DEFINITION_FIELD_NAMES:
                    collected["tool_definition_fields"].append(str(child))
                walk(child)
        elif isinstance(current, list):
            for child in current:
                walk(child)

    walk(value)
    return collected


def merge_evidence(
    destination: dict[str, list[str]], source: dict[str, list[str]]
) -> None:
    for key, values in source.items():
        destination[key].extend(values)


def confidential_findings(value: Any, path: str = "$") -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if isinstance(value, dict):
        role_value = value.get("role")
        role = role_value.casefold() if isinstance(role_value, str) else None
        if role in {"developer", "system"}:
            content = value.get("content")
            if not (
                isinstance(content, str)
                and content.startswith(REDACTION_PREFIX)
            ):
                findings.append(
                    {"category": f"{role}_message", "json_path": path}
                )
        for key, child in value.items():
            category = confidential_field_category(
                key=key,
                ancestors=tuple(path.split(".")),
                message_role=role,
            )
            content_bearing = isinstance(child, (dict, list, str))
            scan_summary = (
                isinstance(child, dict)
                and set(child).issubset({"count", "paths"})
                and isinstance(child.get("count"), int)
                and isinstance(child.get("paths"), list)
            )
            if category is not None and content_bearing and not scan_summary:
                if not (
                    isinstance(child, str)
                    and child.startswith((REDACTION_PREFIX, REMOVAL_PREFIX))
                ):
                    findings.append(
                        {
                            "category": category,
                            "json_path": json_path(path, key),
                        }
                    )
            findings.extend(confidential_findings(child, json_path(path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(
                confidential_findings(child, json_path(path, index))
            )
    elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            nested = json.loads(value)
        except json.JSONDecodeError:
            pass
        else:
            findings.extend(confidential_findings(nested, f"{path}::<json>"))
    return findings


def scan_files_for_secrets(
    paths: Iterable[Path],
    *,
    relative_to: Path | None = None,
) -> dict[str, Any]:
    counts: collections.Counter[str] = collections.Counter()
    finding_paths: dict[str, set[str]] = collections.defaultdict(set)
    scanned_bytes = 0
    scanned_files = 0
    for path in sorted(paths):
        if not path.is_file():
            continue
        data = path.read_bytes()
        scanned_bytes += len(data)
        scanned_files += 1
        text = data.decode("utf-8", errors="replace")
        for category, _ in iter_secret_matches(text):
            counts[category] += 1
            if relative_to is not None:
                try:
                    reported_path = path.relative_to(relative_to).as_posix()
                except ValueError:
                    reported_path = path.name
            else:
                reported_path = path.as_posix()
            finding_paths[category].add(reported_path)
    return {
        "scanned_files": scanned_files,
        "scanned_bytes": scanned_bytes,
        "total_matches": sum(counts.values()),
        "categories": {
            category: {
                "count": counts[category],
                "paths": sorted(finding_paths[category]),
            }
            for category in sorted(
                {pattern.category for pattern in SECRET_PATTERNS}
            )
        },
    }


def validate_publishable_json(paths: Iterable[Path]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in sorted(paths):
        if path.suffix == ".jsonl":
            values = iter_jsonl(path)
        elif path.suffix == ".json":
            values = (read_json(path),)
        else:
            continue
        for index, value in enumerate(values, start=1):
            for finding in confidential_findings(value):
                findings.append(
                    {
                        **finding,
                        "source_file": path.as_posix(),
                        "record": str(index),
                    }
                )
    return findings


def file_integrity(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "line_count": data.count(b"\n"),
    }


def write_integrity_manifest(output_root: Path) -> dict[str, Any]:
    integrity_path = output_root / "artifact-integrity.json"
    evidence_files = [
        path
        for path in output_root.rglob("*")
        if path.is_file() and path != integrity_path
    ]
    records = [file_integrity(path, output_root) for path in sorted(evidence_files)]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "sha256",
        "files": records,
        "summary": {
            "file_count": len(records),
            "total_size_bytes": sum(item["size_bytes"] for item in records),
            "largest_file_bytes": max(
                (item["size_bytes"] for item in records), default=0
            ),
        },
        "self_integrity": {
            "mode": (
                "SHA-256 of canonical JSON excluding self_integrity; exact file "
                "self-hashing is intentionally avoided."
            )
        },
    }
    canonical = dict(manifest)
    canonical.pop("self_integrity")
    manifest["self_integrity"]["canonical_sha256"] = hashlib.sha256(
        canonical_bytes(canonical)
    ).hexdigest()
    write_json(integrity_path, manifest)
    return manifest


def current_branch(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip()
    return branch or None


def sanitize_run(
    *,
    source_root: Path,
    output_root: Path,
    repo_root: Path,
    package_branch: str | None = None,
    package_commit: str | None = None,
    publication_metadata_path: Path | None = None,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    repo_root = repo_root.resolve()
    if not source_root.is_dir():
        raise ValueError(f"Source run directory does not exist: {source_root}")
    if source_root == output_root or source_root in output_root.parents:
        raise ValueError("Output must not be inside the read-only source run")
    if package_commit is not None and not re.fullmatch(
        r"[0-9a-f]{40}", package_commit
    ):
        raise ValueError("Package commit must be a 40-character lowercase SHA")
    raw_manifest = read_json(source_root / "run-manifest.json")
    branch = package_branch if package_branch is not None else current_branch(repo_root)
    metadata_path = publication_metadata_path
    if metadata_path is None:
        retained_metadata = output_root / "publication-metadata.json"
        if retained_metadata.is_file():
            metadata_path = retained_metadata
    publication_metadata = (
        validate_publication_metadata(
            read_json(metadata_path),
            raw_manifest=raw_manifest,
            package_branch=branch,
        )
        if metadata_path is not None
        else {
            "schema_version": SCHEMA_VERSION,
            "pull_requests": {},
            "release": None,
        }
    )
    reset_output(output_root)
    recorder = RedactionRecorder()
    source_evidence: dict[str, list[str]] = collections.defaultdict(list)
    output_evidence: dict[str, list[str]] = collections.defaultdict(list)
    if metadata_path is not None:
        sanitized_publication = sanitize_document(
            publication_metadata,
            source_file="publication-metadata.json",
            recorder=recorder,
        )
        write_json(
            output_root / "publication-metadata.json",
            sanitized_publication,
        )
    repository_roots = {
        Path(value).resolve()
        for value in (
            raw_manifest.get("worktree_root"),
            raw_manifest.get("repository", {}).get("canonical_clone"),
            *(
                child.get("worktree")
                for child in raw_manifest.get("children", [])
                if isinstance(child, dict)
            ),
        )
        if isinstance(value, str) and value.startswith("/")
    }

    prompt_records = copy_prompts(source_root, output_root)

    otel_sources = sorted((source_root / "raw").glob("*.jsonl"))
    if len(otel_sources) != 10:
        raise ValueError(
            f"Expected exactly 10 OTel capture files, found {len(otel_sources)}"
        )
    capture_records: list[dict[str, Any]] = []
    for source in otel_sources:
        sanitized_records: list[Any] = []
        source_count = 0
        for raw_record in iter_jsonl(source):
            source_count += 1
            merge_evidence(
                source_evidence,
                collect_preserved_evidence(raw_record),
            )
            sanitized = sanitize_document(
                raw_record,
                source_file=f"raw/{source.name}",
                recorder=recorder,
            )
            merge_evidence(
                output_evidence,
                collect_preserved_evidence(sanitized),
            )
            sanitized_records.append(sanitized)
        destination = output_root / "otel" / source.name
        write_jsonl(destination, sanitized_records)
        capture_records.append(
            {
                "path": destination.relative_to(output_root).as_posix(),
                "record_count": source_count,
            }
        )

    audit_records = []
    for raw_record in iter_jsonl(source_root / "driver-audit.jsonl"):
        sanitized = sanitize_document(
            raw_record,
            source_file="driver-audit.jsonl",
            recorder=recorder,
        )
        audit_records.append(
            normalize_artifact_paths(
                sanitized,
                source_file="driver-audit.jsonl",
                source_root=source_root,
                recorder=recorder,
            )
        )
    write_jsonl(output_root / "driver-audit.jsonl", audit_records)

    for source in sorted((source_root / "usage").glob("*.json")):
        raw = read_json(source)
        sanitized = sanitize_document(
            raw,
            source_file=f"usage/{source.name}",
            recorder=recorder,
        )
        normalized = normalize_usage_paths(
            sanitized,
            source_file=f"usage/{source.name}",
            source_root=source_root,
            repository_roots=repository_roots,
            recorder=recorder,
        )
        write_json(output_root / "usage" / source.name, normalized)

    excluded_validation = {"run-failure.json"}
    for source in sorted((source_root / "validation").glob("*.json")):
        if source.name in excluded_validation:
            recorder.record(
                category="stale_intermediate_error",
                source_file=f"validation/{source.name}",
                path="$",
                key="<document>",
                original=read_json(source),
                kind="REMOVED",
            )
            continue
        raw = read_json(source)
        sanitized = sanitize_document(
            raw,
            source_file=f"validation/{source.name}",
            recorder=recorder,
        )
        normalized = normalize_artifact_paths(
            sanitized,
            source_file=f"validation/{source.name}",
            source_root=source_root,
            recorder=recorder,
        )
        write_json(output_root / "validation" / source.name, normalized)

    manifest = normalize_manifest(
        raw_manifest,
        source_root=source_root,
        package_branch=branch,
        package_commit=package_commit,
        publication_metadata=publication_metadata,
        recorder=recorder,
    )
    manifest = sanitize_document(
        manifest,
        source_file="manifest.json",
        recorder=recorder,
    )
    write_json(output_root / "manifest.json", manifest)

    preservation: dict[str, Any] = {}
    evidence_categories = sorted(set(source_evidence) | set(output_evidence))
    for category in evidence_categories:
        source_hash = hash_collection(source_evidence.get(category, []))
        output_hash = hash_collection(output_evidence.get(category, []))
        preservation[category] = {
            "source": source_hash,
            "output": output_hash,
            "exact_match": source_hash == output_hash,
        }

    json_paths = [
        path
        for path in output_root.rglob("*")
        if path.is_file() and path.suffix in JSON_SUFFIXES
    ]
    confidentiality_findings = validate_publishable_json(json_paths)
    if confidentiality_findings:
        raise ValueError(
            "Publishable JSON still contains confidential structural fields: "
            f"{len(confidentiality_findings)} finding(s)"
        )

    secret_scan = scan_files_for_secrets(
        (path for path in output_root.rglob("*") if path.is_file()),
        relative_to=output_root,
    )
    if secret_scan["total_matches"]:
        raise ValueError(
            "Publishable output failed secret scan: "
            f"{secret_scan['total_matches']} category/path finding(s)"
        )

    validation_summary = {
        "schema_version": SCHEMA_VERSION,
        "capture_files": capture_records,
        "prompt_copies": prompt_records,
        "preservation": preservation,
        "publication_metadata": {
            "path": (
                "publication-metadata.json"
                if metadata_path is not None
                else None
            ),
            "pull_request_count": len(
                publication_metadata.get("pull_requests", {})
            ),
            "release_present": publication_metadata.get("release") is not None,
            "manifest_matches": all(
                child.get("pull_request")
                == publication_metadata.get("pull_requests", {}).get(
                    child.get("branch")
                )
                for child in manifest.get("children", [])
            ),
        },
        "confidential_structural_findings": 0,
        "secret_scan": secret_scan,
    }
    write_json(
        output_root / "validation" / "sanitization-validation.json",
        validation_summary,
    )
    write_json(output_root / "redaction-report.json", recorder.report())
    integrity = write_integrity_manifest(output_root)
    return {
        "manifest": manifest,
        "redactions": recorder.report()["summary"],
        "integrity": integrity["summary"],
        "validation": validation_summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        type=Path,
        help="Read-only lineage run directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("telemetry/run-2"),
        help="Publishable output directory",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used for Git metadata",
    )
    parser.add_argument(
        "--package-branch",
        help="Override the package branch recorded in the public manifest",
    )
    parser.add_argument(
        "--package-commit",
        help="Published evidence commit recorded in the public manifest",
    )
    parser.add_argument(
        "--publication-metadata",
        type=Path,
        help=(
            "Approved PR/release metadata overlay. If omitted, an existing "
            "output/publication-metadata.json is retained and validated."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = sanitize_run(
        source_root=args.source,
        output_root=args.output,
        repo_root=args.repo_root,
        package_branch=args.package_branch,
        package_commit=args.package_commit,
        publication_metadata_path=args.publication_metadata,
    )
    print(
        json.dumps(
            {
                "output": args.output.as_posix(),
                "redactions": summary["redactions"],
                "integrity": summary["integrity"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
