"""Read-only inventory provider for LM Studio APIs and model storage."""

from __future__ import annotations

import json
import math
import os
import socket
from collections import defaultdict
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, NoReturn
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .errors import (
    ProviderFailureError,
    ProviderUnavailableError,
    UnsupportedOperationError,
)
from .models import ModelRecord, Operation, ProviderResult, ProviderStatus

DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_TIMEOUT = 5.0
DEFAULT_MODEL_ROOTS = (Path.home() / ".lmstudio" / "models",)
MODEL_FILE_SUFFIXES = frozenset(
    {".bin", ".gguf", ".mlx", ".onnx", ".pt", ".pth", ".safetensors"}
)


@dataclass(frozen=True, slots=True)
class LMStudioConfig:
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    model_roots: tuple[Path, ...] = DEFAULT_MODEL_ROOTS

    def __post_init__(self) -> None:
        normalized_url = self.base_url.rstrip("/")
        parsed = urlsplit(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("LM Studio base URL must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("LM Studio base URL must not include a query or fragment")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("LM Studio timeout must be a finite number greater than zero")

        roots: list[Path] = []
        for root in self.model_roots:
            path = Path(root).expanduser().resolve(strict=False)
            if path not in roots:
                roots.append(path)
        object.__setattr__(self, "base_url", normalized_url)
        object.__setattr__(self, "model_roots", tuple(roots))


class LMStudioProvider:
    name = "lm-studio"

    def __init__(self, config: LMStudioConfig | None = None) -> None:
        self.config = config if config is not None else LMStudioConfig()

    def run(self, operation: Operation) -> ProviderResult:
        if operation is not Operation.LIST:
            raise UnsupportedOperationError(self.name, operation.value)

        api_records: list[ModelRecord] = []
        file_records: list[ModelRecord] = []
        issues: list[tuple[ProviderStatus, str]] = []

        try:
            api_records = self._parse_api_records(self._fetch_models(), operation)
        except ProviderUnavailableError as error:
            issues.append(
                (ProviderStatus.UNAVAILABLE, f"API discovery failed: {error.reason}")
            )
        except ProviderFailureError as error:
            issues.append((ProviderStatus.ERROR, f"API discovery failed: {error.reason}"))

        file_records, file_errors = self._discover_files()
        issues.extend(
            (ProviderStatus.ERROR, f"filesystem discovery failed: {error}")
            for error in file_errors
        )

        records = tuple(self._deduplicate(api_records, file_records))
        if not issues:
            return ProviderResult.success(self.name, operation, records)

        status = (
            ProviderStatus.ERROR
            if any(item_status is ProviderStatus.ERROR for item_status, _ in issues)
            else ProviderStatus.UNAVAILABLE
        )
        return ProviderResult.failure(
            self.name,
            operation,
            status,
            "; ".join(message for _, message in issues),
            records,
        )

    def _fetch_models(self) -> object:
        endpoint = f"{self.config.base_url}/models"
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

    def _parse_api_records(
        self, payload: object, operation: Operation
    ) -> list[ModelRecord]:
        if not isinstance(payload, dict) or "data" not in payload:
            self._malformed(operation, "expected an object containing 'data'")
        models = payload["data"]
        if not isinstance(models, list):
            self._malformed(operation, "'data' must be an array")

        records: list[ModelRecord] = []
        for index, model in enumerate(models):
            if not isinstance(model, dict):
                self._malformed(operation, f"data[{index}] must be an object")
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                self._malformed(
                    operation, f"data[{index}].id must be a non-empty string"
                )

            attributes = {"source": "api"}
            for key in ("object", "owned_by"):
                value = model.get(key)
                if value is not None:
                    if not isinstance(value, str):
                        self._malformed(
                            operation, f"data[{index}].{key} must be a string"
                        )
                    attributes[f"api.{key}"] = value
            created = model.get("created")
            if created is not None:
                if (
                    not isinstance(created, int)
                    or isinstance(created, bool)
                    or created < 0
                ):
                    self._malformed(
                        operation,
                        f"data[{index}].created must be a non-negative integer",
                    )
                attributes["api.created"] = str(created)

            records.append(
                ModelRecord(
                    provider=self.name,
                    model_id=model_id,
                    attributes=attributes,
                )
            )
        return records

    def _discover_files(self) -> tuple[list[ModelRecord], list[str]]:
        records: list[ModelRecord] = []
        errors: list[str] = []
        for root in self.config.model_roots:
            try:
                if not root.exists():
                    raise FileNotFoundError("root does not exist")
                if not root.is_dir():
                    raise NotADirectoryError("root is not a directory")
            except OSError as error:
                errors.append(f"{root}: {error}")
                continue

            walk_errors: list[OSError] = []
            for directory, directory_names, file_names in os.walk(
                root, onerror=walk_errors.append
            ):
                directory_names.sort()
                for file_name in sorted(file_names):
                    path = Path(directory, file_name)
                    if path.suffix.lower() not in MODEL_FILE_SUFFIXES:
                        continue
                    try:
                        if not path.is_file():
                            continue
                        size = path.stat().st_size
                    except OSError as error:
                        errors.append(f"{path}: {error}")
                        continue
                    relative_path = path.relative_to(root)
                    model_id = relative_path.with_suffix("").as_posix()
                    records.append(
                        ModelRecord(
                            provider=self.name,
                            model_id=model_id,
                            size_bytes=size,
                            location=str(path),
                            attributes={
                                "filesystem.extension": path.suffix.lower(),
                                "filesystem.relative_path": relative_path.as_posix(),
                                "filesystem.root": str(root),
                                "source": "filesystem",
                            },
                        )
                    )
            errors.extend(
                f"{Path(error.filename) if error.filename else root}: {error}"
                for error in walk_errors
            )
        return records, errors

    def _deduplicate(
        self,
        api_records: list[ModelRecord],
        file_records: list[ModelRecord],
    ) -> list[ModelRecord]:
        api_by_id: dict[str, list[ModelRecord]] = defaultdict(list)
        for record in api_records:
            api_by_id[record.model_id].append(record)

        merged_api = {
            model_id: self._merge_api_records(records)
            for model_id, records in api_by_id.items()
        }
        matched_ids: set[str] = set()
        output: list[ModelRecord] = []
        seen_files: set[tuple[str, str | None]] = set()
        for record in sorted(
            file_records, key=lambda item: (item.model_id, item.location or "")
        ):
            file_key = (record.model_id, record.location)
            if file_key in seen_files:
                continue
            seen_files.add(file_key)
            api_record = merged_api.get(record.model_id)
            if api_record is None:
                output.append(record)
                continue
            matched_ids.add(record.model_id)
            attributes = dict(api_record.attributes)
            attributes.update(record.attributes)
            attributes["source"] = "api,filesystem"
            output.append(
                ModelRecord(
                    provider=self.name,
                    model_id=record.model_id,
                    size_bytes=record.size_bytes,
                    location=record.location,
                    attributes=attributes,
                )
            )

        output.extend(
            record
            for model_id, record in sorted(merged_api.items())
            if model_id not in matched_ids
        )
        return output

    def _merge_api_records(self, records: list[ModelRecord]) -> ModelRecord:
        model_id = records[0].model_id
        values: dict[str, set[str]] = defaultdict(set)
        for record in records:
            for key, value in record.attributes.items():
                values[key].add(value)
        attributes = {
            key: (
                next(iter(items))
                if len(items) == 1
                else json.dumps(sorted(items), separators=(",", ":"))
            )
            for key, items in values.items()
        }
        return ModelRecord(
            provider=self.name,
            model_id=model_id,
            attributes=attributes,
        )

    def _malformed(self, operation: Operation, reason: str) -> NoReturn:
        raise ProviderFailureError(
            self.name, operation.value, f"malformed response: {reason}"
        )
