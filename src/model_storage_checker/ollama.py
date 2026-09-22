"""Ollama model inventory provider."""

from __future__ import annotations

import json
import math
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import CheckerError, ErrorCode
from .models import ModelRecord
from .providers import ModelProvider, ProviderStatus
from .results import OperationResult

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT = 2.0


class OllamaProvider(ModelProvider):
    """Read model records from Ollama's local HTTP API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self._endpoint = f"{base_url.rstrip('/')}/api/tags"
        self._timeout = timeout
        self._status_result: (
            OperationResult[tuple[ModelRecord, ...]] | None
        ) = None

    @property
    def name(self) -> str:
        return "ollama"

    def status(self) -> ProviderStatus:
        result = self._fetch_models()
        self._status_result = result
        unavailable = next(
            (
                error
                for error in result.errors
                if error.code is ErrorCode.PROVIDER_UNAVAILABLE
            ),
            None,
        )
        if unavailable is not None:
            return ProviderStatus(
                name=self.name,
                available=False,
                message=unavailable.message,
            )
        return ProviderStatus(name=self.name, available=True)

    def list_models(self) -> OperationResult[tuple[ModelRecord, ...]]:
        if self._status_result is not None:
            result = self._status_result
            self._status_result = None
            return result
        return self._fetch_models()

    def _fetch_models(self) -> OperationResult[tuple[ModelRecord, ...]]:
        try:
            request = Request(
                self._endpoint,
                headers={"Accept": "application/json"},
                method="GET",
            )
            with urlopen(request, timeout=self._timeout) as response:
                payload = json.load(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            return self._provider_error(
                "Ollama API returned malformed JSON.",
                {"endpoint": self._endpoint, "reason": str(error)},
            )
        except ValueError as error:
            return self._provider_error(
                "Ollama API endpoint is invalid.",
                {"endpoint": self._endpoint, "reason": str(error)},
            )
        except HTTPError as error:
            return self._provider_error(
                f"Ollama API returned HTTP {error.code}.",
                {"endpoint": self._endpoint, "status": error.code},
            )
        except (URLError, TimeoutError, socket.timeout, OSError) as error:
            reason = getattr(error, "reason", error)
            return OperationResult.failure(
                CheckerError(
                    code=ErrorCode.PROVIDER_UNAVAILABLE,
                    message=f"Ollama is unavailable at {self._endpoint}: {reason}",
                    provider=self.name,
                    details={"endpoint": self._endpoint},
                )
            )

        try:
            models = self._parse_payload(payload)
        except (TypeError, ValueError) as error:
            return self._provider_error(
                "Ollama API returned a malformed model inventory.",
                {"endpoint": self._endpoint, "reason": str(error)},
            )
        return OperationResult.success(models)

    def _parse_payload(self, payload: Any) -> tuple[ModelRecord, ...]:
        if not isinstance(payload, dict):
            raise TypeError("response must be an object")
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise TypeError("'models' must be a list")

        records: list[ModelRecord] = []
        for index, raw_model in enumerate(raw_models):
            if not isinstance(raw_model, dict):
                raise TypeError(f"models[{index}] must be an object")

            name = raw_model.get("model") or raw_model.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"models[{index}] has no model or name")

            digest = raw_model.get("digest")
            if digest is not None and (
                not isinstance(digest, str) or not digest.strip()
            ):
                raise TypeError(f"models[{index}].digest must be a string")
            identifier = digest or name

            size = raw_model.get("size")
            if size is not None and (
                isinstance(size, bool) or not isinstance(size, int) or size < 0
            ):
                raise TypeError(
                    f"models[{index}].size must be a non-negative integer"
                )

            metadata: dict[str, Any] = {}
            modified_at = raw_model.get("modified_at")
            if modified_at is not None:
                if not isinstance(modified_at, str):
                    raise TypeError(
                        f"models[{index}].modified_at must be a string"
                    )
                metadata["modified_at"] = modified_at

            details = raw_model.get("details")
            if details is not None:
                if not isinstance(details, dict):
                    raise TypeError(
                        f"models[{index}].details must be an object"
                    )
                metadata["details"] = details

            records.append(
                ModelRecord(
                    provider=self.name,
                    identifier=identifier,
                    name=name,
                    size_bytes=size,
                    metadata=metadata,
                )
            )
        return tuple(records)

    def _provider_error(
        self, message: str, details: dict[str, Any]
    ) -> OperationResult[tuple[ModelRecord, ...]]:
        return OperationResult.failure(
            CheckerError(
                code=ErrorCode.PROVIDER_ERROR,
                message=message,
                provider=self.name,
                details=details,
            )
        )
