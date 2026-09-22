"""Docker image and container inventory provider."""

from __future__ import annotations

import json
import math
import re
import subprocess
from typing import Any, Callable, Sequence

from .errors import CheckerError, ErrorCode
from .models import ModelRecord
from .providers import ModelProvider, ProviderStatus
from .results import OperationResult

DEFAULT_EXECUTABLE = "docker"
DEFAULT_TIMEOUT = 5.0

_IMAGE_COMMAND = (
    "image",
    "ls",
    "--all",
    "--no-trunc",
    "--digests",
    "--format",
    "{{json .}}",
)
_CONTAINER_COMMAND = (
    "container",
    "ls",
    "--all",
    "--no-trunc",
    "--size",
    "--format",
    "{{json .}}",
)
_SIZE_PATTERN = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>B|kB|MB|GB|TB|PB|KiB|MiB|GiB|TiB|PiB)?\s*$",
    re.IGNORECASE,
)
_VIRTUAL_SIZE_PATTERN = re.compile(r"\(virtual\s+(?P<size>[^)]+)\)", re.I)
_AI_MARKERS = {
    "ollama": "Ollama",
    "localai": "LocalAI",
    "local-ai": "LocalAI",
    "vllm": "vLLM",
    "llama.cpp": "llama.cpp",
    "llama-cpp": "llama.cpp",
}


class DockerProvider(ModelProvider):
    """Read all local image and container records using the Docker CLI."""

    def __init__(
        self,
        executable: str = DEFAULT_EXECUTABLE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not executable.strip():
            raise ValueError("executable must not be empty")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self._executable = executable
        self._timeout = timeout
        self._status_result: (
            OperationResult[tuple[ModelRecord, ...]] | None
        ) = None

    @property
    def name(self) -> str:
        return "docker"

    def status(self) -> ProviderStatus:
        result = self._inventory()
        self._status_result = result
        if result.succeeded:
            return ProviderStatus(name=self.name, available=True)
        error = result.errors[0]
        return ProviderStatus(
            name=self.name,
            available=error.code is not ErrorCode.PROVIDER_UNAVAILABLE,
            message=error.message,
        )

    def list_models(self) -> OperationResult[tuple[ModelRecord, ...]]:
        if self._status_result is not None:
            result = self._status_result
            self._status_result = None
            return result
        return self._inventory()

    def _inventory(self) -> OperationResult[tuple[ModelRecord, ...]]:
        image_output = self._run(_IMAGE_COMMAND, "images")
        if isinstance(image_output, CheckerError):
            return OperationResult.failure(image_output)
        container_output = self._run(_CONTAINER_COMMAND, "containers")
        if isinstance(container_output, CheckerError):
            return OperationResult.failure(container_output)

        try:
            images = self._parse_lines(
                image_output, "images", self._image_record
            )
            containers = self._parse_lines(
                container_output, "containers", self._container_record
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return OperationResult.failure(
                self._error(
                    ErrorCode.PROVIDER_ERROR,
                    "Docker CLI returned malformed inventory output.",
                    {
                        "reason": "malformed_output",
                        "error": str(error),
                    },
                )
            )
        return OperationResult.success((*images, *containers))

    def _run(
        self, arguments: Sequence[str], resource: str
    ) -> str | CheckerError:
        command = [self._executable, *arguments]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError:
            return self._error(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"Docker CLI executable '{self._executable}' was not found.",
                {
                    "reason": "cli_missing",
                    "executable": self._executable,
                    "command": command,
                },
            )
        except subprocess.TimeoutExpired:
            return self._error(
                ErrorCode.PROVIDER_ERROR,
                f"Docker {resource} inventory timed out.",
                {
                    "reason": "command_timeout",
                    "command": command,
                    "timeout_seconds": self._timeout,
                },
            )
        except UnicodeDecodeError as error:
            return self._error(
                ErrorCode.PROVIDER_ERROR,
                f"Docker {resource} inventory returned malformed text.",
                {
                    "reason": "malformed_output",
                    "command": command,
                    "error": str(error),
                },
            )
        except PermissionError as error:
            return self._error(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "Permission denied while executing the Docker CLI.",
                {
                    "reason": "permission_denied",
                    "command": command,
                    "error": str(error),
                },
            )
        except OSError as error:
            return self._error(
                ErrorCode.PROVIDER_ERROR,
                f"Unable to execute Docker {resource} inventory.",
                {
                    "reason": "command_failure",
                    "command": command,
                    "error": str(error),
                },
            )

        if completed.returncode == 0:
            return completed.stdout

        stderr = completed.stderr.strip()
        lowered = stderr.casefold()
        if "permission denied" in lowered:
            code = ErrorCode.PROVIDER_UNAVAILABLE
            reason = "permission_denied"
            message = "Permission denied while accessing Docker."
        elif any(
            marker in lowered
            for marker in (
                "cannot connect to the docker daemon",
                "is the docker daemon running",
                "error during connect",
                "docker daemon is not running",
            )
        ):
            code = ErrorCode.PROVIDER_UNAVAILABLE
            reason = "daemon_unavailable"
            message = "Docker daemon is unavailable."
        else:
            code = ErrorCode.PROVIDER_ERROR
            reason = "command_failure"
            message = f"Docker {resource} inventory command failed."
        return self._error(
            code,
            message,
            {
                "reason": reason,
                "command": command,
                "exit_code": completed.returncode,
                "stderr": stderr,
            },
        )

    def _parse_lines(
        self,
        output: str,
        resource: str,
        convert: Callable[[dict[str, Any], int], ModelRecord],
    ) -> tuple[ModelRecord, ...]:
        records: list[ModelRecord] = []
        for line_number, line in enumerate(output.splitlines(), start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise TypeError(
                    f"{resource} line {line_number} must be a JSON object"
                )
            records.append(convert(raw, line_number))
        return tuple(records)

    def _image_record(
        self, raw: dict[str, Any], line_number: int
    ) -> ModelRecord:
        image_id = self._required_string(raw, "ID", "images", line_number)
        repository = self._required_string(
            raw, "Repository", "images", line_number
        )
        tag = self._required_string(raw, "Tag", "images", line_number)
        dangling = repository == "<none>" or tag == "<none>"
        reference = image_id if dangling else f"{repository}:{tag}"
        virtual_size = self._optional_size(
            raw, "VirtualSize", "images", line_number
        )
        if virtual_size is None:
            virtual_size = self._optional_size(
                raw, "Size", "images", line_number
            )
        shared_size = self._optional_size(
            raw, "SharedSize", "images", line_number
        )
        metadata: dict[str, Any] = {
            "resource_type": "image",
            "image_id": image_id,
            "repository": repository,
            "tag": tag,
            "dangling": dangling,
            "virtual_size_bytes": virtual_size,
            "shared_size_bytes": shared_size,
            "local_ai_classification": self._classification(
                repository, tag, str(raw.get("Labels", ""))
            ),
        }
        self._copy_metadata(
            raw,
            metadata,
            {
                "CreatedAt": "created_at",
                "Digest": "digest",
                "Containers": "container_count",
                "Labels": "labels",
                "UniqueSize": "unique_size",
            },
        )
        return ModelRecord(
            provider=self.name,
            identifier=f"image:{image_id}:{reference}",
            name=reference,
            size_bytes=virtual_size,
            metadata=metadata,
        )

    def _container_record(
        self, raw: dict[str, Any], line_number: int
    ) -> ModelRecord:
        container_id = self._required_string(
            raw, "ID", "containers", line_number
        )
        name = self._required_string(raw, "Names", "containers", line_number)
        image = self._required_string(
            raw, "Image", "containers", line_number
        )
        state = self._required_string(
            raw, "State", "containers", line_number
        )
        size_text = self._optional_string(
            raw, "Size", "containers", line_number
        )
        writable_size, virtual_size = self._container_sizes(size_text)
        metadata: dict[str, Any] = {
            "resource_type": "container",
            "container_id": container_id,
            "image": image,
            "state": state,
            "running": state.casefold() == "running",
            "writable_size_bytes": writable_size,
            "virtual_size_bytes": virtual_size,
            "local_ai_classification": self._classification(
                name, image, str(raw.get("Labels", ""))
            ),
        }
        self._copy_metadata(
            raw,
            metadata,
            {
                "Status": "status",
                "CreatedAt": "created_at",
                "ImageID": "image_id",
                "Labels": "labels",
                "Mounts": "mounts",
                "Networks": "networks",
                "Ports": "ports",
                "Command": "command",
            },
        )
        return ModelRecord(
            provider=self.name,
            identifier=f"container:{container_id}",
            name=name,
            size_bytes=writable_size,
            metadata=metadata,
        )

    @staticmethod
    def _required_string(
        raw: dict[str, Any],
        field: str,
        resource: str,
        line_number: int,
    ) -> str:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{resource} line {line_number}.{field} "
                "must be a non-empty string"
            )
        return value

    @staticmethod
    def _optional_string(
        raw: dict[str, Any],
        field: str,
        resource: str,
        line_number: int,
    ) -> str | None:
        value = raw.get(field)
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise TypeError(
                f"{resource} line {line_number}.{field} must be a string"
            )
        return value

    def _optional_size(
        self,
        raw: dict[str, Any],
        field: str,
        resource: str,
        line_number: int,
    ) -> int | None:
        value = self._optional_string(raw, field, resource, line_number)
        if value is None or value in {"N/A", "-"}:
            return None
        return self._parse_size(value)

    @staticmethod
    def _parse_size(value: str) -> int:
        match = _SIZE_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError(f"invalid Docker size: {value!r}")
        unit = (match.group("unit") or "B").casefold()
        powers = {
            "b": 1,
            "kb": 1_000,
            "mb": 1_000_000,
            "gb": 1_000_000_000,
            "tb": 1_000_000_000_000,
            "pb": 1_000_000_000_000_000,
            "kib": 1 << 10,
            "mib": 1 << 20,
            "gib": 1 << 30,
            "tib": 1 << 40,
            "pib": 1 << 50,
        }
        return round(float(match.group("value")) * powers[unit])

    def _container_sizes(
        self, value: str | None
    ) -> tuple[int | None, int | None]:
        if value is None:
            return None, None
        virtual_match = _VIRTUAL_SIZE_PATTERN.search(value)
        virtual_size = (
            self._parse_size(virtual_match.group("size"))
            if virtual_match is not None
            else None
        )
        writable_text = value.split("(", maxsplit=1)[0].strip()
        return self._parse_size(writable_text), virtual_size

    @staticmethod
    def _copy_metadata(
        raw: dict[str, Any],
        metadata: dict[str, Any],
        fields: dict[str, str],
    ) -> None:
        for source, destination in fields.items():
            value = raw.get(source)
            if value not in (None, ""):
                if not isinstance(value, str):
                    raise TypeError(f"{source} must be a string")
                metadata[destination] = value

    @staticmethod
    def _classification(*values: str) -> dict[str, Any]:
        text = " ".join(values).casefold()
        matches = sorted(
            {label for marker, label in _AI_MARKERS.items() if marker in text}
        )
        return {
            "heuristic": True,
            "likely_local_ai": bool(matches),
            "matches": matches,
        }

    def _error(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any],
    ) -> CheckerError:
        return CheckerError(
            code=code,
            message=message,
            provider=self.name,
            details=details,
        )
