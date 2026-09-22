"""Read-only Docker image and container inventory via the Docker CLI."""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass
from json import JSONDecodeError
from typing import NoReturn

from .errors import (
    ProviderFailureError,
    ProviderUnavailableError,
    UnsupportedOperationError,
)
from .models import ModelRecord, Operation, ProviderResult

DEFAULT_TIMEOUT = 10.0
_JSON_TEMPLATE = "{{json .}}"
_IMAGE_COMMAND = (
    "docker",
    "image",
    "ls",
    "--all",
    "--no-trunc",
    "--digests",
    "--format",
    _JSON_TEMPLATE,
)
_CONTAINER_COMMAND = (
    "docker",
    "container",
    "ls",
    "--all",
    "--no-trunc",
    "--size",
    "--format",
    _JSON_TEMPLATE,
)
_IMAGE_FIELDS = frozenset({"ID", "Repository", "Tag", "Digest", "CreatedAt", "Size"})
_CONTAINER_FIELDS = frozenset(
    {"ID", "Image", "Command", "CreatedAt", "State", "Status", "Size", "Names"}
)
_SIZE_PATTERN = re.compile(
    r"^(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>B|kB|MB|GB|TB|PB|KiB|MiB|GiB|TiB|PiB)"
)
_SIZE_FACTORS = {
    "B": 1,
    "kB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "PB": 1000**5,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
    "PiB": 1024**5,
}
_AI_TERMS = (
    "comfyui",
    "diffusion",
    "huggingface",
    "keras",
    "ollama",
    "llama",
    "pytorch",
    "stable-diffusion",
    "tensorflow",
    "text-generation",
    "vllm",
)


@dataclass(frozen=True, slots=True)
class DockerConfig:
    timeout: float = DEFAULT_TIMEOUT
    classify_ai: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Docker timeout must be a finite number greater than zero")


class DockerProvider:
    name = "docker"

    def __init__(self, config: DockerConfig | None = None) -> None:
        self.config = config if config is not None else DockerConfig()

    def run(self, operation: Operation) -> ProviderResult:
        if operation is not Operation.LIST:
            raise UnsupportedOperationError(self.name, operation.value)

        image_output = self._invoke(_IMAGE_COMMAND, "image inventory")
        container_output = self._invoke(_CONTAINER_COMMAND, "container inventory")
        records = (
            *self._parse_records(image_output, "image", _IMAGE_FIELDS),
            *self._parse_records(container_output, "container", _CONTAINER_FIELDS),
        )
        return ProviderResult.success(self.name, operation, records)

    def _invoke(self, command: tuple[str, ...], inventory_name: str) -> str:
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
            )
        except FileNotFoundError as error:
            raise ProviderUnavailableError(
                self.name, "Docker CLI is missing"
            ) from error
        except PermissionError as error:
            raise ProviderUnavailableError(
                self.name, "permission denied while executing the Docker CLI"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ProviderUnavailableError(
                self.name,
                f"{inventory_name} timed out after {self.config.timeout:g} seconds",
            ) from error
        except OSError as error:
            raise ProviderUnavailableError(
                self.name, f"cannot execute the Docker CLI: {error}"
            ) from error

        if completed.returncode != 0:
            diagnostic = completed.stderr.lower()
            if "permission denied" in diagnostic:
                raise ProviderUnavailableError(
                    self.name, "permission denied while accessing Docker"
                )
            if any(
                marker in diagnostic
                for marker in (
                    "cannot connect to the docker daemon",
                    "failed to connect to the docker api",
                    "error during connect",
                    "is the docker daemon running",
                    "docker daemon is not running",
                    "connection refused",
                )
            ):
                raise ProviderUnavailableError(
                    self.name, "Docker daemon is unavailable"
                )
            raise ProviderFailureError(
                self.name,
                Operation.LIST.value,
                f"{inventory_name} command exited with status {completed.returncode}",
            )
        return completed.stdout

    def _parse_records(
        self,
        output: str,
        kind: str,
        required_fields: frozenset[str],
    ) -> tuple[ModelRecord, ...]:
        records: list[ModelRecord] = []
        for line_number, line in enumerate(output.splitlines(), start=1):
            if not line.strip():
                self._malformed(kind, line_number, "blank JSON line")
            try:
                item = json.loads(line)
            except JSONDecodeError as error:
                self._malformed(kind, line_number, "invalid JSON")
            if not isinstance(item, dict):
                self._malformed(kind, line_number, "expected a JSON object")
            if any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in item.items()
            ):
                self._malformed(kind, line_number, "all fields must be strings")
            missing = sorted(required_fields - item.keys())
            if missing:
                self._malformed(
                    kind,
                    line_number,
                    f"missing fields: {', '.join(missing)}",
                )
            identifier = item["ID"]
            if not identifier:
                self._malformed(kind, line_number, "ID must not be empty")

            attributes = {f"docker.{key}": value for key, value in item.items()}
            attributes["inventory.kind"] = kind
            if kind == "container":
                attributes["image.relationship"] = item["Image"]
                location = item["Names"] or None
            else:
                location = self._image_reference(item)
            if self.config.classify_ai:
                self._add_ai_heuristic(attributes, item)
            records.append(
                ModelRecord(
                    provider=self.name,
                    model_id=f"{kind}:{identifier}",
                    size_bytes=self._size_bytes(item["Size"], kind, line_number),
                    location=location,
                    attributes=attributes,
                )
            )
        return tuple(records)

    def _size_bytes(self, value: str, kind: str, line_number: int) -> int:
        match = _SIZE_PATTERN.match(value)
        if match is None:
            self._malformed(kind, line_number, "Size has an unsupported format")
        number = float(match.group("number"))
        return round(number * _SIZE_FACTORS[match.group("unit")])

    @staticmethod
    def _image_reference(item: dict[str, str]) -> str | None:
        repository = item["Repository"]
        tag = item["Tag"]
        if repository == "<none>":
            return None
        if tag == "<none>":
            return repository
        return f"{repository}:{tag}"

    @staticmethod
    def _add_ai_heuristic(
        attributes: dict[str, str], item: dict[str, str]
    ) -> None:
        searchable = " ".join(item.values()).lower()
        match = next((term for term in _AI_TERMS if term in searchable), None)
        attributes["heuristic.ai_related"] = "true" if match else "false"
        attributes["heuristic.classification"] = "optional"
        attributes["heuristic.match"] = match or "none"

    def _malformed(self, kind: str, line_number: int, reason: str) -> NoReturn:
        raise ProviderFailureError(
            self.name,
            Operation.LIST.value,
            f"malformed Docker {kind} output at line {line_number}: {reason}",
        )
