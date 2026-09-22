"""Read-only inventory provider for a local Ollama service."""

from __future__ import annotations

import json
import math
import socket
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, NoReturn
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .errors import (
    ProviderFailureError,
    ProviderUnavailableError,
    UnsupportedOperationError,
)
from .models import ModelRecord, Operation, ProviderResult

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT

    def __post_init__(self) -> None:
        normalized_url = self.base_url.rstrip("/")
        parsed = urlsplit(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Ollama base URL must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("Ollama base URL must not include a query or fragment")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Ollama timeout must be a finite number greater than zero")
        object.__setattr__(self, "base_url", normalized_url)


class OllamaProvider:
    name = "ollama"

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config if config is not None else OllamaConfig()

    def run(self, operation: Operation) -> ProviderResult:
        if operation is not Operation.LIST:
            raise UnsupportedOperationError(self.name, operation.value)

        payload = self._fetch_tags()
        records = self._parse_records(payload, operation)
        return ProviderResult.success(self.name, operation, tuple(records))

    def _fetch_tags(self) -> object:
        endpoint = f"{self.config.base_url}/api/tags"
        request = Request(
            endpoint,
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                body = response.read()
        except (URLError, TimeoutError, socket.timeout, OSError) as error:
            reason = getattr(error, "reason", error)
            raise ProviderUnavailableError(
                self.name, f"cannot reach {endpoint}: {reason}"
            ) from error

        try:
            return json.loads(body)
        except (JSONDecodeError, UnicodeDecodeError) as error:
            raise ProviderFailureError(
                self.name, Operation.LIST.value, "response is not valid JSON"
            ) from error

    def _parse_records(
        self, payload: object, operation: Operation
    ) -> list[ModelRecord]:
        if not isinstance(payload, dict) or "models" not in payload:
            self._malformed(operation, "expected an object containing 'models'")
        models = payload["models"]
        if not isinstance(models, list):
            self._malformed(operation, "'models' must be an array")

        records: list[ModelRecord] = []
        for index, model in enumerate(models):
            if not isinstance(model, dict):
                self._malformed(operation, f"models[{index}] must be an object")
            records.append(self._record_from_model(model, index, operation))
        return records

    def _record_from_model(
        self, model: dict[str, Any], index: int, operation: Operation
    ) -> ModelRecord:
        name = model.get("name")
        if not isinstance(name, str) or not name:
            self._malformed(
                operation, f"models[{index}].name must be a non-empty string"
            )

        size = model.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            self._malformed(
                operation, f"models[{index}].size must be a non-negative integer"
            )

        attributes: dict[str, str] = {}
        self._copy_string(model, "digest", attributes, index, operation)
        self._copy_string(model, "modified_at", attributes, index, operation)

        details = model.get("details")
        if details is not None:
            if not isinstance(details, dict):
                self._malformed(operation, f"models[{index}].details must be an object")
            for key in (
                "family",
                "format",
                "parameter_size",
                "quantization_level",
            ):
                self._copy_string(
                    details, key, attributes, index, operation, prefix="details."
                )

        return ModelRecord(
            provider=self.name,
            model_id=name,
            size_bytes=size,
            attributes=attributes,
        )

    def _copy_string(
        self,
        source: dict[str, Any],
        key: str,
        target: dict[str, str],
        index: int,
        operation: Operation,
        *,
        prefix: str = "",
    ) -> None:
        value = source.get(key)
        if value is None:
            return
        if not isinstance(value, str):
            self._malformed(
                operation, f"models[{index}].{prefix}{key} must be a string"
            )
        target[key] = value

    def _malformed(self, operation: Operation, reason: str) -> NoReturn:
        raise ProviderFailureError(
            self.name, operation.value, f"malformed response: {reason}"
        )
