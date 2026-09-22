#!/usr/bin/env python3
"""Build the offline lineage dashboard data from sanitized evidence and Git."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = 1
PROVENANCE_OTEL = "captured in OTel"
PROVENANCE_AUDIT = "driver audit"
PROVENANCE_GIT = "Git commit/trailer"
PROVENANCE_GITHUB = "planned/live GitHub metadata"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def integrity_record(path: Path, reported_path: str) -> dict[str, Any]:
    data = path.read_bytes()
    record = {
        "path": reported_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }
    if path.suffix.casefold() == ".xlsx":
        record["line_count"] = None
        record["media_type"] = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        record["line_count"] = data.count(b"\n")
        record["media_type"] = (
            "application/json"
            if path.suffix.casefold() == ".json"
            else "text/plain"
        )
    return record


def update_integrity_for_dashboard(
    *,
    telemetry_root: Path,
    dashboard_path: Path,
    repo_root: Path,
) -> None:
    integrity_path = telemetry_root / "artifact-integrity.json"
    if not integrity_path.is_file():
        return
    integrity = read_json(integrity_path)
    try:
        reported_path = dashboard_path.relative_to(repo_root).as_posix()
    except ValueError:
        reported_path = dashboard_path.name
    external_paths = [dashboard_path]
    workbook_path = (
        repo_root
        / "docs"
        / "lineage"
        / "model-storage-checker-lineage-run-2.xlsx"
    )
    if workbook_path.is_file():
        external_paths.append(workbook_path)
    external_records = []
    for path in sorted(external_paths):
        try:
            path_label = path.relative_to(repo_root).as_posix()
        except ValueError:
            path_label = path.name
        external_records.append(integrity_record(path, path_label))
    integrity["external_generated_files"] = external_records
    internal_files = [
        integrity_record(path, path.relative_to(telemetry_root).as_posix())
        for path in sorted(telemetry_root.rglob("*"))
        if path.is_file() and path != integrity_path
    ]
    integrity["files"] = internal_files
    all_records = [*internal_files, *external_records]
    integrity["summary"] = {
        "file_count": len(all_records),
        "total_size_bytes": sum(
            item.get("size_bytes", 0) for item in all_records
        ),
        "largest_file_bytes": max(
            (item.get("size_bytes", 0) for item in all_records),
            default=0,
        ),
        "telemetry_file_count": len(internal_files),
        "external_file_count": len(external_records),
    }
    canonical = dict(integrity)
    canonical.pop("self_integrity", None)
    integrity["self_integrity"] = {
        "mode": (
            "SHA-256 of canonical JSON excluding self_integrity; exact file "
            "self-hashing is intentionally avoided."
        ),
        "canonical_sha256": hashlib.sha256(
            canonical_bytes(canonical)
        ).hexdigest(),
    }
    write_json(integrity_path, integrity)


def parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def counter_dict(counter: collections.Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def sum_numeric(attributes: dict[str, Any], keys: Iterable[str]) -> int:
    total = 0
    for key in keys:
        value = attributes.get(key)
        if isinstance(value, (int, float)):
            total += int(value)
    return total


def summarize_capture(path: Path) -> dict[str, Any]:
    records = list(iter_jsonl(path))
    spans = [record for record in records if "spanId" in record]
    resource_attributes: dict[str, Any] = {}
    for record in records:
        resource = record.get("resource", {})
        attributes = resource.get("attributes", {})
        if isinstance(attributes, dict) and attributes:
            resource_attributes.update(attributes)

    traces: dict[str, dict[str, Any]] = {}
    models: collections.Counter[str] = collections.Counter()
    tools: collections.Counter[str] = collections.Counter()
    span_names: collections.Counter[str] = collections.Counter()
    model_turns: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    token_totals = {
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_write": 0,
        "reasoning": 0,
    }

    for span in spans:
        attributes = span.get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}
        trace_id = str(span.get("traceId", ""))
        trace = traces.setdefault(
            trace_id,
            {
                "trace_id": trace_id,
                "span_count": 0,
                "span_names": collections.Counter(),
                "models": collections.Counter(),
                "tools": collections.Counter(),
                "start_time": span.get("startTime"),
                "end_time": span.get("endTime"),
            },
        )
        trace["span_count"] += 1
        span_name = str(span.get("name", "unnamed span"))
        trace["span_names"][span_name] += 1
        span_names[span_name] += 1
        if span.get("startTime") is not None:
            trace["start_time"] = min(
                trace["start_time"] or span["startTime"], span["startTime"]
            )
        if span.get("endTime") is not None:
            trace["end_time"] = max(
                trace["end_time"] or span["endTime"], span["endTime"]
            )

        request_model = attributes.get("gen_ai.request.model")
        response_model = attributes.get("gen_ai.response.model")
        for model in (request_model, response_model):
            if isinstance(model, str) and model:
                models[model] += 1
                trace["models"][model] += 1

        tool_name = attributes.get("gen_ai.tool.name")
        if isinstance(tool_name, str) and tool_name:
            tools[tool_name] += 1
            trace["tools"][tool_name] += 1

        token_totals["input"] += sum_numeric(
            attributes, ("gen_ai.usage.input_tokens",)
        )
        token_totals["output"] += sum_numeric(
            attributes, ("gen_ai.usage.output_tokens",)
        )
        token_totals["cache_read"] += sum_numeric(
            attributes, ("gen_ai.usage.cache_read.input_tokens",)
        )
        token_totals["cache_write"] += sum_numeric(
            attributes, ("gen_ai.usage.cache_write.input_tokens",)
        )
        token_totals["reasoning"] += sum_numeric(
            attributes, ("gen_ai.usage.reasoning.output_tokens",)
        )

        input_messages = attributes.get("gen_ai.input.messages")
        output_messages = attributes.get("gen_ai.output.messages")
        if input_messages is not None or output_messages is not None:
            model_turns.append(
                {
                    "trace_id": trace_id,
                    "span_id": span.get("spanId"),
                    "start_time": span.get("startTime"),
                    "end_time": span.get("endTime"),
                    "request_model": request_model,
                    "response_model": response_model,
                    "input_messages": parse_json_string(input_messages),
                    "output_messages": parse_json_string(output_messages),
                    "finish_reasons": attributes.get(
                        "gen_ai.response.finish_reasons"
                    ),
                    "usage": {
                        "input_tokens": attributes.get(
                            "gen_ai.usage.input_tokens"
                        ),
                        "output_tokens": attributes.get(
                            "gen_ai.usage.output_tokens"
                        ),
                        "cache_read_tokens": attributes.get(
                            "gen_ai.usage.cache_read.input_tokens"
                        ),
                        "cache_write_tokens": attributes.get(
                            "gen_ai.usage.cache_write.input_tokens"
                        ),
                        "reasoning_tokens": attributes.get(
                            "gen_ai.usage.reasoning.output_tokens"
                        ),
                    },
                }
            )

        arguments = attributes.get("gen_ai.tool.call.arguments")
        if arguments is not None:
            tool_calls.append(
                {
                    "trace_id": trace_id,
                    "span_id": span.get("spanId"),
                    "start_time": span.get("startTime"),
                    "end_time": span.get("endTime"),
                    "tool_name": tool_name or span_name,
                    "tool_type": attributes.get("gen_ai.tool.type"),
                    "call_id": attributes.get("gen_ai.tool.call.id"),
                    "arguments": parse_json_string(arguments),
                    "result": parse_json_string(
                        attributes.get("gen_ai.tool.call.result")
                    ),
                    "status": span.get("status"),
                }
            )

    trace_summaries = []
    for trace in traces.values():
        trace_summaries.append(
            {
                **{
                    key: trace[key]
                    for key in (
                        "trace_id",
                        "span_count",
                        "start_time",
                        "end_time",
                    )
                },
                "span_names": counter_dict(trace["span_names"]),
                "models": counter_dict(trace["models"]),
                "tools": counter_dict(trace["tools"]),
            }
        )
    trace_summaries.sort(key=lambda item: (str(item["start_time"]), item["trace_id"]))

    return {
        "name": path.stem,
        "path": path.as_posix(),
        "record_count": len(records),
        "span_count": len(spans),
        "metric_record_count": len(records) - len(spans),
        "trace_count": len(traces),
        "resource": resource_attributes,
        "models": counter_dict(models),
        "tools": counter_dict(tools),
        "span_names": counter_dict(span_names),
        "token_totals": token_totals,
        "traces": trace_summaries,
        "model_turns": model_turns,
        "tool_calls": tool_calls,
    }


def git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def parse_trailers(message: str) -> list[dict[str, str]]:
    trailers: list[dict[str, str]] = []
    for line in message.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key and key.replace("-", "").isalnum() and value.strip():
            trailers.append({"key": key, "value": value.strip()})
    return trailers


def git_commit(repo_root: Path, commit_sha: str) -> dict[str, Any]:
    raw = git_output(
        repo_root,
        "show",
        "-s",
        "--format=%H%x00%P%x00%T%x00%s%x00%B",
        commit_sha,
    ).rstrip("\n")
    sha, parents, tree, subject, message = raw.split("\x00", 4)
    return {
        "sha": sha,
        "parents": parents.split() if parents else [],
        "tree": tree,
        "subject": subject,
        "message": message.strip(),
        "trailers": parse_trailers(message),
    }


def git_branches(repo_root: Path) -> dict[str, str]:
    output = git_output(
        repo_root,
        "for-each-ref",
        "--format=%(refname:short)%00%(objectname)",
        "refs/heads",
    )
    branches: dict[str, str] = {}
    for line in output.splitlines():
        if "\x00" not in line:
            continue
        name, sha = line.split("\x00", 1)
        branches[name] = sha
    return branches


def read_audit(path: Path) -> dict[str, Any]:
    by_session: dict[str, dict[str, Any]] = {}
    total = 0
    for record in iter_jsonl(path):
        total += 1
        session_id = str(record.get("session_id") or "unknown")
        summary = by_session.setdefault(
            session_id,
            {
                "record_count": 0,
                "events": collections.Counter(),
                "roles": collections.Counter(),
            },
        )
        summary["record_count"] += 1
        summary["events"][str(record.get("event") or "unknown")] += 1
        summary["roles"][str(record.get("role") or "unknown")] += 1
    return {
        "record_count": total,
        "sessions": {
            session_id: {
                "record_count": summary["record_count"],
                "events": counter_dict(summary["events"]),
                "roles": counter_dict(summary["roles"]),
            }
            for session_id, summary in sorted(by_session.items())
        },
    }


def read_usage(usage_root: Path) -> dict[str, Any]:
    summaries = {}
    for path in sorted(usage_root.glob("*.json")):
        value = read_json(path)
        token_details = value.get("tokenDetails", {})
        summaries[path.stem] = {
            "total_user_requests": value.get("totalUserRequests"),
            "total_premium_request_cost": value.get("totalPremiumRequestCost"),
            "total_nano_aiu": value.get("totalNanoAiu"),
            "total_api_duration_ms": value.get("totalApiDurationMs"),
            "current_model": value.get("currentModel"),
            "tokens": {
                name: details.get("tokenCount")
                for name, details in token_details.items()
                if isinstance(details, dict)
            },
            "code_changes": value.get("codeChanges", {}),
            "model_metrics": value.get("modelMetrics", {}),
        }
    return summaries


def node(
    node_id: str,
    label: str,
    kind: str,
    *,
    layer: int | None = None,
    session_id: str | None = None,
    status: str = "verified",
    provenance: Iterable[str] = (),
    summary: str = "",
    expandable: bool = False,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "kind": kind,
        "layer": layer,
        "session_id": session_id,
        "status": status,
        "provenance": list(provenance),
        "summary": summary,
        "expandable": expandable,
    }


def edge(
    source: str,
    target: str,
    label: str,
    *,
    provenance: str,
    primary: bool = False,
) -> dict[str, Any]:
    return {
        "id": f"{source}->{target}:{label}",
        "source": source,
        "target": target,
        "label": label,
        "provenance": provenance,
        "primary": primary,
    }


def publication_for_branch(
    branch: str,
    child: dict[str, Any] | None,
    publication_metadata: dict[str, Any],
) -> Any:
    live = publication_metadata.get("pull_requests", {}).get(branch)
    if live is not None:
        return live
    if child is not None:
        return child.get("pull_request")
    return None


def build_dashboard(
    *,
    telemetry_root: Path,
    output_path: Path,
    repo_root: Path,
    publication_metadata_path: Path | None = None,
) -> dict[str, Any]:
    telemetry_root = telemetry_root.resolve()
    output_path = output_path.resolve()
    repo_root = repo_root.resolve()
    manifest = read_json(telemetry_root / "manifest.json")
    if publication_metadata_path is None:
        retained_metadata = telemetry_root / "publication-metadata.json"
        if retained_metadata.is_file():
            publication_metadata_path = retained_metadata
    publication_metadata = (
        read_json(publication_metadata_path)
        if publication_metadata_path is not None
        else {}
    )
    audit = read_audit(telemetry_root / "driver-audit.jsonl")
    usage = read_usage(telemetry_root / "usage")
    captures = [
        summarize_capture(path)
        for path in sorted((telemetry_root / "otel").glob("*.jsonl"))
    ]
    branches = git_branches(repo_root)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    expansions: dict[str, dict[str, list[dict[str, Any]]]] = {}

    parent = manifest["parent"]
    parent_session_id = parent["session_id"]
    prompt_path = telemetry_root / parent["evidence"]["prompt"]
    origin_id = "origin-prompt"
    parent_id = f"session:{parent_session_id}"
    nodes.append(
        node(
            origin_id,
            "Origin prompt",
            "prompt",
            status="captured",
            provenance=(PROVENANCE_OTEL,),
            summary="Exact explicit orchestrator prompt copied after secret scan.",
        )
    )
    details[origin_id] = {
        "title": "Origin prompt",
        "content_type": "text/markdown",
        "content": prompt_path.read_text(encoding="utf-8"),
        "evidence_path": parent["evidence"]["prompt"],
        "provenance": [PROVENANCE_OTEL],
    }
    nodes.append(
        node(
            parent_id,
            "Parent orchestrator",
            "session",
            session_id=parent_session_id,
            status=parent.get("status") or "verified",
            provenance=(PROVENANCE_OTEL, PROVENANCE_AUDIT),
            summary="Logical parent session coordinating five stacked layers.",
        )
    )
    details[parent_id] = {
        "title": "Parent orchestrator",
        "session_id": parent_session_id,
        "status": parent.get("status"),
        "started_at": parent.get("started_at"),
        "ended_at": parent.get("ended_at"),
        "verification": parent.get("verification"),
        "audit": audit["sessions"].get(parent_session_id),
        "provenance": [PROVENANCE_OTEL, PROVENANCE_AUDIT],
    }
    edges.append(
        edge(
            origin_id,
            parent_id,
            "initiates",
            provenance=PROVENANCE_OTEL,
            primary=True,
        )
    )

    children_by_session = {
        child["session_id"]: child for child in manifest.get("children", [])
    }
    captures_by_session: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for capture in captures:
        session_id = str(capture["resource"].get("poc.session_id") or "")
        captures_by_session[session_id].append(capture)
    for session_captures in captures_by_session.values():
        session_captures.sort(
            key=lambda item: (
                str(item["resource"].get("poc.attempt") or ""),
                item["name"],
            )
        )

    commit_nodes: dict[int, str] = {}
    branch_nodes: dict[int, str] = {}
    pr_nodes: dict[int, str] = {}
    total_tool_calls = 0
    total_model_turns = 0
    all_models: collections.Counter[str] = collections.Counter()
    all_tools: collections.Counter[str] = collections.Counter()

    ordered_sessions = [(parent_session_id, None)] + [
        (child["session_id"], child)
        for child in sorted(
            manifest.get("children", []), key=lambda item: item["layer"]
        )
    ]
    for session_id, child in ordered_sessions:
        layer = child.get("layer") if child else None
        session_node_id = parent_id if child is None else f"session:{session_id}"
        if child is not None:
            prompt_relative = child["evidence"]["prompt"]
            prompt_text = (telemetry_root / prompt_relative).read_text(
                encoding="utf-8"
            )
            nodes.append(
                node(
                    session_node_id,
                    f"Layer {layer}: {child['layer_name']}",
                    "session",
                    layer=layer,
                    session_id=session_id,
                    status=child.get("status") or "verified",
                    provenance=(PROVENANCE_OTEL, PROVENANCE_AUDIT),
                    summary=child.get("commit_subject") or "",
                )
            )
            details[session_node_id] = {
                "title": f"Layer {layer}: {child['layer_name']}",
                "session_id": session_id,
                "parent_session_id": child.get("parent_session_id"),
                "branch": child.get("branch"),
                "base_branch": child.get("base_branch"),
                "status": child.get("status"),
                "prompt": prompt_text,
                "prompt_path": prompt_relative,
                "verification": child.get("verification"),
                "tests": child.get("tests"),
                "audit": audit["sessions"].get(session_id),
                "provenance": [PROVENANCE_OTEL, PROVENANCE_AUDIT],
            }
            edges.append(
                edge(
                    parent_id,
                    session_node_id,
                    "delegates",
                    provenance=PROVENANCE_AUDIT,
                    primary=True,
                )
            )

        final_model_node: str | None = None
        final_tool_node: str | None = None
        for attempt_index, capture in enumerate(
            captures_by_session.get(session_id, []), start=1
        ):
            attempt_id = f"attempt:{capture['name']}"
            traces_id = f"traces:{capture['name']}"
            models_id = f"models:{capture['name']}"
            tools_id = f"tools:{capture['name']}"
            invocation = capture["resource"].get("poc.invocation")
            attempt_label = (
                str(invocation)
                if invocation
                else f"process attempt {attempt_index}"
            )
            nodes.append(
                node(
                    attempt_id,
                    attempt_label,
                    "process",
                    layer=layer,
                    session_id=session_id,
                    status="captured",
                    provenance=(PROVENANCE_OTEL, PROVENANCE_AUDIT),
                    summary=(
                        f"{capture['record_count']} records; "
                        f"{capture['span_count']} spans"
                    ),
                )
            )
            details[attempt_id] = {
                "title": attempt_label,
                "capture": capture["name"],
                "resource_attributes": capture["resource"],
                "record_count": capture["record_count"],
                "span_count": capture["span_count"],
                "metric_record_count": capture["metric_record_count"],
                "evidence_path": Path(capture["path"])
                .relative_to(telemetry_root)
                .as_posix(),
                "provenance": [PROVENANCE_OTEL, PROVENANCE_AUDIT],
            }
            edges.append(
                edge(
                    session_node_id,
                    attempt_id,
                    "launches",
                    provenance=PROVENANCE_AUDIT,
                    primary=True,
                )
            )

            nodes.append(
                node(
                    traces_id,
                    f"{capture['trace_count']} traces",
                    "trace-group",
                    layer=layer,
                    session_id=session_id,
                    status="captured",
                    provenance=(PROVENANCE_OTEL,),
                    summary=f"{capture['span_count']} spans",
                    expandable=bool(capture["traces"]),
                )
            )
            details[traces_id] = {
                "title": f"Trace summary: {capture['name']}",
                "trace_count": capture["trace_count"],
                "span_count": capture["span_count"],
                "span_names": capture["span_names"],
                "provenance": [PROVENANCE_OTEL],
            }
            edges.append(
                edge(
                    attempt_id,
                    traces_id,
                    "emits",
                    provenance=PROVENANCE_OTEL,
                    primary=True,
                )
            )

            trace_nodes = []
            trace_edges = []
            for trace in capture["traces"]:
                trace_node_id = f"trace:{capture['name']}:{trace['trace_id']}"
                trace_nodes.append(
                    node(
                        trace_node_id,
                        trace["trace_id"][:12],
                        "trace",
                        layer=layer,
                        session_id=session_id,
                        status="captured",
                        provenance=(PROVENANCE_OTEL,),
                        summary=f"{trace['span_count']} spans",
                    )
                )
                trace_edges.append(
                    edge(
                        traces_id,
                        trace_node_id,
                        "contains",
                        provenance=PROVENANCE_OTEL,
                    )
                )
                details[trace_node_id] = {
                    "title": f"Trace {trace['trace_id']}",
                    **trace,
                    "provenance": [PROVENANCE_OTEL],
                }
            expansions[traces_id] = {
                "nodes": trace_nodes,
                "edges": trace_edges,
            }

            model_count = sum(capture["models"].values())
            nodes.append(
                node(
                    models_id,
                    "Model activity",
                    "model-group",
                    layer=layer,
                    session_id=session_id,
                    status="captured",
                    provenance=(PROVENANCE_OTEL,),
                    summary=(
                        f"{len(capture['model_turns'])} turns; "
                        f"{model_count} model observations"
                    ),
                    expandable=bool(capture["models"]),
                )
            )
            details[models_id] = {
                "title": f"Model activity: {capture['name']}",
                "models": capture["models"],
                "token_totals": capture["token_totals"],
                "turns": capture["model_turns"],
                "usage_summary": usage.get(capture["name"]),
                "provenance": [PROVENANCE_OTEL],
            }
            edges.append(
                edge(
                    traces_id,
                    models_id,
                    "records",
                    provenance=PROVENANCE_OTEL,
                    primary=True,
                )
            )
            model_nodes = []
            model_edges = []
            for model_name, count in capture["models"].items():
                model_node_id = f"model:{capture['name']}:{model_name}"
                model_nodes.append(
                    node(
                        model_node_id,
                        model_name,
                        "model",
                        layer=layer,
                        session_id=session_id,
                        status="captured",
                        provenance=(PROVENANCE_OTEL,),
                        summary=f"{count} observations",
                    )
                )
                model_edges.append(
                    edge(
                        models_id,
                        model_node_id,
                        "uses",
                        provenance=PROVENANCE_OTEL,
                    )
                )
                details[model_node_id] = {
                    "title": model_name,
                    "observation_count": count,
                    "turns": [
                        turn
                        for turn in capture["model_turns"]
                        if model_name
                        in {turn.get("request_model"), turn.get("response_model")}
                    ],
                    "provenance": [PROVENANCE_OTEL],
                }
            expansions[models_id] = {
                "nodes": model_nodes,
                "edges": model_edges,
            }

            nodes.append(
                node(
                    tools_id,
                    "Tool activity",
                    "tool-group",
                    layer=layer,
                    session_id=session_id,
                    status="captured",
                    provenance=(PROVENANCE_OTEL,),
                    summary=f"{len(capture['tool_calls'])} captured calls",
                    expandable=bool(capture["tools"]),
                )
            )
            details[tools_id] = {
                "title": f"Tool activity: {capture['name']}",
                "tools": capture["tools"],
                "calls": capture["tool_calls"],
                "provenance": [PROVENANCE_OTEL],
            }
            edges.append(
                edge(
                    traces_id,
                    tools_id,
                    "records",
                    provenance=PROVENANCE_OTEL,
                )
            )
            tool_nodes = []
            tool_edges = []
            for tool_name, count in capture["tools"].items():
                tool_node_id = f"tool:{capture['name']}:{tool_name}"
                tool_nodes.append(
                    node(
                        tool_node_id,
                        tool_name,
                        "tool",
                        layer=layer,
                        session_id=session_id,
                        status="captured",
                        provenance=(PROVENANCE_OTEL,),
                        summary=f"{count} spans",
                    )
                )
                tool_edges.append(
                    edge(
                        tools_id,
                        tool_node_id,
                        "invokes",
                        provenance=PROVENANCE_OTEL,
                    )
                )
                details[tool_node_id] = {
                    "title": tool_name,
                    "span_count": count,
                    "calls": [
                        call
                        for call in capture["tool_calls"]
                        if call["tool_name"] == tool_name
                    ],
                    "provenance": [PROVENANCE_OTEL],
                }
            expansions[tools_id] = {
                "nodes": tool_nodes,
                "edges": tool_edges,
            }

            final_model_node = models_id
            final_tool_node = tools_id
            total_tool_calls += len(capture["tool_calls"])
            total_model_turns += len(capture["model_turns"])
            all_models.update(capture["models"])
            all_tools.update(capture["tools"])

        if child is None:
            continue
        commit_sha = child.get("commit_sha")
        if not commit_sha:
            continue
        commit = git_commit(repo_root, commit_sha)
        commit_id = f"commit:{commit_sha}"
        commit_nodes[layer] = commit_id
        nodes.append(
            node(
                commit_id,
                commit["subject"],
                "commit",
                layer=layer,
                session_id=session_id,
                status="verified",
                provenance=(PROVENANCE_GIT,),
                summary=commit_sha[:12],
            )
        )
        details[commit_id] = {
            "title": commit["subject"],
            **commit,
            "manifest_parent_sha": child.get("parent_sha"),
            "manifest_tree_sha": child.get("tree_sha"),
            "provenance": [PROVENANCE_GIT],
        }
        if final_model_node is not None:
            edges.append(
                edge(
                    final_model_node,
                    commit_id,
                    "produces",
                    provenance=PROVENANCE_GIT,
                    primary=True,
                )
            )
        if final_tool_node is not None:
            edges.append(
                edge(
                    final_tool_node,
                    commit_id,
                    "supports",
                    provenance=PROVENANCE_OTEL,
                )
            )

        branch = child["branch"]
        branch_id = f"branch:{branch}"
        branch_nodes[layer] = branch_id
        local_sha = branches.get(branch)
        branch_status = "verified" if local_sha == commit_sha else "planned"
        nodes.append(
            node(
                branch_id,
                branch,
                "branch",
                layer=layer,
                session_id=session_id,
                status=branch_status,
                provenance=(PROVENANCE_GIT, PROVENANCE_GITHUB),
                summary=(
                    f"local ref {local_sha[:12]}"
                    if local_sha
                    else "local ref not present"
                ),
            )
        )
        details[branch_id] = {
            "title": branch,
            "branch": branch,
            "expected_commit": commit_sha,
            "local_commit": local_sha,
            "matches_expected_commit": local_sha == commit_sha,
            "provenance": [PROVENANCE_GIT, PROVENANCE_GITHUB],
        }
        edges.append(
            edge(
                commit_id,
                branch_id,
                "points to",
                provenance=PROVENANCE_GIT,
                primary=True,
            )
        )

        pull_request = publication_for_branch(
            branch, child, publication_metadata
        )
        pr_id = f"pr:{branch}"
        pr_nodes[layer] = pr_id
        pr_label = (
            f"PR #{pull_request['number']}"
            if isinstance(pull_request, dict) and pull_request.get("number")
            else "PR pending approval"
        )
        nodes.append(
            node(
                pr_id,
                pr_label,
                "pull-request",
                layer=layer,
                session_id=session_id,
                status="live" if pull_request else "placeholder",
                provenance=(PROVENANCE_GITHUB,),
                summary=branch,
            )
        )
        details[pr_id] = {
            "title": pr_label,
            "branch": branch,
            "metadata": pull_request,
            "provenance": [PROVENANCE_GITHUB],
        }
        edges.append(
            edge(
                branch_id,
                pr_id,
                "publishes as",
                provenance=PROVENANCE_GITHUB,
                primary=True,
            )
        )

    for layer in sorted(commit_nodes):
        next_layer = layer + 1
        if next_layer in commit_nodes:
            edges.append(
                edge(
                    commit_nodes[layer],
                    commit_nodes[next_layer],
                    "parent of",
                    provenance=PROVENANCE_GIT,
                )
            )

    package_branch = manifest.get("package", {}).get("package_branch")
    package_branch_id: str | None = None
    package_pr_id: str | None = None
    if package_branch and package_branch not in {
        child["branch"] for child in manifest.get("children", [])
    }:
        package_branch_id = f"branch:{package_branch}"
        local_sha = branches.get(package_branch)
        nodes.append(
            node(
                package_branch_id,
                package_branch,
                "branch",
                layer=6,
                status="working-tree",
                provenance=(PROVENANCE_GIT, PROVENANCE_GITHUB),
                summary=(
                    "Lineage evidence package; commit intentionally pending."
                ),
            )
        )
        details[package_branch_id] = {
            "title": package_branch,
            "branch": package_branch,
            "local_head": local_sha,
            "package_commit": manifest.get("package", {}).get("package_commit"),
            "provenance": [PROVENANCE_GIT, PROVENANCE_GITHUB],
        }
        if commit_nodes:
            edges.append(
                edge(
                    commit_nodes[max(commit_nodes)],
                    package_branch_id,
                    "base for",
                    provenance=PROVENANCE_GIT,
                    primary=True,
                )
            )
        package_pull_request = publication_metadata.get("pull_requests", {}).get(
            package_branch
        )
        package_pr_id = f"pr:{package_branch}"
        nodes.append(
            node(
                package_pr_id,
                (
                    f"PR #{package_pull_request['number']}"
                    if isinstance(package_pull_request, dict)
                    and package_pull_request.get("number")
                    else "Package PR pending approval"
                ),
                "pull-request",
                layer=6,
                status="live" if package_pull_request else "placeholder",
                provenance=(PROVENANCE_GITHUB,),
                summary=package_branch,
            )
        )
        details[package_pr_id] = {
            "title": "Lineage package pull request",
            "branch": package_branch,
            "metadata": package_pull_request,
            "provenance": [PROVENANCE_GITHUB],
        }
        edges.append(
            edge(
                package_branch_id,
                package_pr_id,
                "publishes as",
                provenance=PROVENANCE_GITHUB,
                primary=True,
            )
        )

    release_metadata = publication_metadata.get("release") or manifest.get(
        "release"
    )
    release_id = "release"
    release_label = (
        str(release_metadata.get("name") or release_metadata.get("tag"))
        if isinstance(release_metadata, dict)
        else "Release pending approval"
    )
    nodes.append(
        node(
            release_id,
            release_label,
            "release",
            layer=6,
            status="live" if release_metadata else "placeholder",
            provenance=(PROVENANCE_GITHUB,),
            summary="Customer-shareable lineage evidence package.",
        )
    )
    details[release_id] = {
        "title": release_label,
        "metadata": release_metadata,
        "provenance": [PROVENANCE_GITHUB],
    }
    release_source = package_pr_id or (
        pr_nodes[max(pr_nodes)] if pr_nodes else None
    )
    if release_source is not None:
        edges.append(
            edge(
                release_source,
                release_id,
                "promotes to",
                provenance=PROVENANCE_GITHUB,
                primary=True,
            )
        )

    layers = [
        {
            "layer": child["layer"],
            "name": child["layer_name"],
            "session_id": child["session_id"],
            "branch": child["branch"],
        }
        for child in sorted(
            manifest.get("children", []), key=lambda item: item["layer"]
        )
    ]
    if package_branch:
        layers.append(
            {
                "layer": 6,
                "name": "Lineage evidence package",
                "session_id": None,
                "branch": package_branch,
            }
        )

    data = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "title": "Copilot lineage evidence",
            "repository": manifest["repository"],
            "package": manifest["package"],
            "orchestration": manifest["orchestration"],
            "limitations": [
                "Host-driven logical parent/child linkage; no operating-system "
                "process nesting is claimed.",
                "No W3C traceparent propagation is claimed across sessions.",
                "Feature pull request nodes use approved live metadata; the "
                "package pull request and release remain placeholders until "
                "publication is explicitly approved.",
            ],
            "provenance_labels": [
                PROVENANCE_OTEL,
                PROVENANCE_AUDIT,
                PROVENANCE_GIT,
                PROVENANCE_GITHUB,
            ],
        },
        "summary": {
            "logical_sessions": 1 + len(manifest.get("children", [])),
            "process_attempts": len(captures),
            "otel_records": sum(item["record_count"] for item in captures),
            "otel_spans": sum(item["span_count"] for item in captures),
            "traces": sum(item["trace_count"] for item in captures),
            "model_turns": total_model_turns,
            "tool_calls": total_tool_calls,
            "models": counter_dict(all_models),
            "tools": counter_dict(all_tools),
            "commits": len(commit_nodes),
            "audit_records": audit["record_count"],
        },
        "filters": {
            "layers": layers,
            "sessions": [
                {
                    "session_id": session_id,
                    "label": (
                        "Parent orchestrator"
                        if child is None
                        else f"Layer {child['layer']}: {child['layer_name']}"
                    ),
                }
                for session_id, child in ordered_sessions
            ],
        },
        "nodes": nodes,
        "edges": edges,
        "expansions": expansions,
        "details": details,
    }
    write_json(output_path, data)
    update_integrity_for_dashboard(
        telemetry_root=telemetry_root,
        dashboard_path=output_path,
        repo_root=repo_root,
    )
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--telemetry-root",
        type=Path,
        default=Path("telemetry/run-2"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/lineage/data.json"),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--publication-metadata",
        type=Path,
        help="Optional approved PR/release metadata overlay",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = build_dashboard(
        telemetry_root=args.telemetry_root,
        output_path=args.output,
        repo_root=args.repo_root,
        publication_metadata_path=args.publication_metadata,
    )
    print(
        json.dumps(
            {
                "output": args.output.as_posix(),
                "nodes": len(data["nodes"]),
                "edges": len(data["edges"]),
                "expansion_groups": len(data["expansions"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
