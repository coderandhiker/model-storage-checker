"""LM Studio API and on-disk model inventory provider."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import socket
import stat
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import CheckerError, ErrorCode
from .models import ModelRecord
from .providers import ModelProvider, ProviderStatus
from .results import OperationResult

DEFAULT_BASE_URL = "http://127.0.0.1:1234"
DEFAULT_TIMEOUT = 2.0
DEFAULT_MODEL_ROOTS = (Path("~/.lmstudio/models"),)
_MODEL_FILE_SUFFIXES = frozenset((".gguf", ".safetensors"))


@dataclass(frozen=True, slots=True)
class _FilesystemInventory:
    records: tuple[ModelRecord, ...]
    missing_roots: tuple[str, ...]


class LMStudioProvider(ModelProvider):
    """Read model records from LM Studio's API and model directories."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        model_roots: Sequence[str | Path] | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")

        configured_roots = (
            DEFAULT_MODEL_ROOTS if model_roots is None else tuple(model_roots)
        )
        if not configured_roots:
            raise ValueError("model_roots must not be empty")

        self._endpoint = f"{base_url.rstrip('/')}/v1/models"
        self._timeout = timeout
        self._model_roots = tuple(
            Path(root).expanduser().absolute() for root in configured_roots
        )
        self._status_result: (
            OperationResult[tuple[ModelRecord, ...]] | None
        ) = None
        self._status_message: str | None = None

    @property
    def name(self) -> str:
        return "lm-studio"

    def status(self) -> ProviderStatus:
        result, message = self._inventory()
        self._status_result = result
        self._status_message = message
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
        return ProviderStatus(
            name=self.name,
            available=True,
            message=message,
        )

    def list_models(self) -> OperationResult[tuple[ModelRecord, ...]]:
        if self._status_result is not None:
            result = self._status_result
            self._status_result = None
            self._status_message = None
            return result
        result, _ = self._inventory()
        return result

    def _inventory(
        self,
    ) -> tuple[OperationResult[tuple[ModelRecord, ...]], str | None]:
        api_records, api_error = self._fetch_api()
        filesystem, filesystem_error = self._scan_filesystem()

        if api_error is not None and api_error.code is ErrorCode.PROVIDER_ERROR:
            return OperationResult.failure(api_error), None
        if filesystem_error is not None:
            return OperationResult.failure(filesystem_error), None
        assert filesystem is not None

        if api_error is not None:
            if not filesystem.records:
                details = dict(api_error.details)
                details["model_roots"] = [
                    str(root) for root in self._model_roots
                ]
                details["missing_model_roots"] = list(
                    filesystem.missing_roots
                )
                all_roots_missing = (
                    len(filesystem.missing_roots)
                    == len(self._model_roots)
                )
                details["filesystem_state"] = (
                    "model_root_absent" if all_roots_missing else "empty"
                )
                message = api_error.message
                if all_roots_missing:
                    message += " The configured model directory is absent."
                return (
                    OperationResult.failure(
                        CheckerError(
                            code=ErrorCode.PROVIDER_UNAVAILABLE,
                            message=message,
                            provider=self.name,
                            details=details,
                        )
                    ),
                    None,
                )
            additional_metadata: dict[str, Any] = {
                "api_unavailable": {
                    "endpoint": self._endpoint,
                    "reason": api_error.message,
                }
            }
            if filesystem.missing_roots:
                additional_metadata["missing_model_roots"] = list(
                    filesystem.missing_roots
                )
            records = tuple(
                self._with_metadata(record, **additional_metadata)
                for record in filesystem.records
            )
            message = (
                "LM Studio API is unavailable; filesystem inventory is "
                "available."
            )
            if filesystem.missing_roots:
                message += " One or more model directories are absent."
            return OperationResult.success(records), message

        assert api_records is not None
        records = self._merge_records(api_records, filesystem.records)
        if filesystem.missing_roots:
            if not records:
                return (
                    OperationResult.failure(
                        CheckerError(
                            code=ErrorCode.PROVIDER_ERROR,
                            message="LM Studio model directory is absent.",
                            provider=self.name,
                            details={
                                "reason": "model_root_absent",
                                "model_roots": list(
                                    filesystem.missing_roots
                                ),
                            },
                        )
                    ),
                    None,
                )
            records = tuple(
                self._with_metadata(
                    record,
                    missing_model_roots=list(filesystem.missing_roots),
                )
                for record in records
            )
            return (
                OperationResult.success(records),
                "One or more LM Studio model directories are absent.",
            )
        return OperationResult.success(records), None

    def _fetch_api(
        self,
    ) -> tuple[tuple[ModelRecord, ...] | None, CheckerError | None]:
        try:
            request = Request(
                self._endpoint,
                headers={"Accept": "application/json"},
                method="GET",
            )
            with urlopen(request, timeout=self._timeout) as response:
                payload = json.load(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            return None, self._error(
                ErrorCode.PROVIDER_ERROR,
                "LM Studio API returned malformed JSON.",
                {"endpoint": self._endpoint, "reason": str(error)},
            )
        except ValueError as error:
            return None, self._error(
                ErrorCode.PROVIDER_ERROR,
                "LM Studio API endpoint is invalid.",
                {"endpoint": self._endpoint, "reason": str(error)},
            )
        except HTTPError as error:
            return None, self._error(
                ErrorCode.PROVIDER_ERROR,
                f"LM Studio API returned HTTP {error.code}.",
                {"endpoint": self._endpoint, "status": error.code},
            )
        except (URLError, TimeoutError, socket.timeout, OSError) as error:
            reason = getattr(error, "reason", error)
            return None, self._error(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"LM Studio is unavailable at {self._endpoint}: {reason}",
                {"endpoint": self._endpoint},
            )

        try:
            return self._parse_api_payload(payload), None
        except (TypeError, ValueError) as error:
            return None, self._error(
                ErrorCode.PROVIDER_ERROR,
                "LM Studio API returned a malformed model inventory.",
                {"endpoint": self._endpoint, "reason": str(error)},
            )

    def _parse_api_payload(self, payload: Any) -> tuple[ModelRecord, ...]:
        if not isinstance(payload, dict):
            raise TypeError("response must be an object")
        raw_models = payload.get("data")
        if not isinstance(raw_models, list):
            raise TypeError("'data' must be a list")

        records: list[ModelRecord] = []
        for index, raw_model in enumerate(raw_models):
            if not isinstance(raw_model, dict):
                raise TypeError(f"data[{index}] must be an object")
            identifier = raw_model.get("id")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError(f"data[{index}].id must be a non-empty string")

            metadata: dict[str, Any] = {
                "source": "api",
                "endpoint": self._endpoint,
            }
            for field in ("object", "owned_by"):
                value = raw_model.get(field)
                if value is not None:
                    if not isinstance(value, str):
                        raise TypeError(
                            f"data[{index}].{field} must be a string"
                        )
                    metadata[field] = value

            created = raw_model.get("created")
            if created is not None:
                if isinstance(created, bool) or not isinstance(created, int):
                    raise TypeError(f"data[{index}].created must be an integer")
                metadata["created"] = created

            records.append(
                ModelRecord(
                    provider=self.name,
                    identifier=identifier,
                    name=identifier,
                    metadata=metadata,
                )
            )
        return tuple(records)

    def _scan_filesystem(
        self,
    ) -> tuple[_FilesystemInventory | None, CheckerError | None]:
        records: list[ModelRecord] = []
        missing_roots: list[str] = []
        try:
            for root in self._model_roots:
                try:
                    root_stat = root.stat()
                except FileNotFoundError:
                    missing_roots.append(str(root))
                    continue
                if not stat.S_ISDIR(root_stat.st_mode):
                    raise NotADirectoryError(f"not a directory: {root}")
                records.extend(self._scan_root(root))
        except OSError as error:
            return None, self._error(
                ErrorCode.PROVIDER_ERROR,
                "Unable to inspect an LM Studio model directory.",
                {
                    "reason": "filesystem_error",
                    "path": str(getattr(error, "filename", None) or root),
                    "error": str(error),
                },
            )

        records.sort(key=lambda record: record.path or record.identifier)
        return (
            _FilesystemInventory(
                records=tuple(records),
                missing_roots=tuple(missing_roots),
            ),
            None,
        )

    def _scan_root(self, root: Path) -> list[ModelRecord]:
        discovered_files: dict[Path, int] = {}
        model_directories: set[Path] = set()

        def raise_walk_error(error: OSError) -> None:
            raise error

        for directory, _, filenames in os.walk(
            root, followlinks=False, onerror=raise_walk_error
        ):
            for filename in sorted(filenames):
                file_path = Path(directory) / filename
                file_stat = file_path.stat(follow_symlinks=False)
                if not stat.S_ISREG(file_stat.st_mode):
                    continue
                discovered_files[file_path] = file_stat.st_size
                if file_path.suffix.casefold() in _MODEL_FILE_SUFFIXES:
                    model_directories.add(
                        self._model_directory(root, file_path.parent)
                    )

        records: list[ModelRecord] = []
        for model_directory in sorted(model_directories):
            files = [
                {"path": str(file_path), "size_bytes": size}
                for file_path, size in sorted(discovered_files.items())
                if file_path.is_relative_to(model_directory)
            ]
            relative_path = model_directory.relative_to(root)
            relative_name = (
                model_directory.name
                if relative_path == Path(".")
                else relative_path.as_posix()
            )
            records.append(
                ModelRecord(
                    provider=self.name,
                    identifier=str(model_directory),
                    name=relative_name,
                    size_bytes=sum(file["size_bytes"] for file in files),
                    path=str(model_directory),
                    metadata={
                        "source": "filesystem",
                        "model_root": str(root),
                        "relative_path": relative_name,
                        "artifacts": files,
                    },
                )
            )
        return records

    @staticmethod
    def _model_directory(root: Path, artifact_parent: Path) -> Path:
        relative_parent = artifact_parent.relative_to(root)
        if len(relative_parent.parts) >= 2:
            return root.joinpath(*relative_parent.parts[:2])
        if relative_parent.parts:
            return root / relative_parent.parts[0]
        return root

    def _merge_records(
        self,
        api_records: tuple[ModelRecord, ...],
        filesystem_records: tuple[ModelRecord, ...],
    ) -> tuple[ModelRecord, ...]:
        candidate_indexes: dict[str, list[int]] = {}
        for index, record in enumerate(filesystem_records):
            for candidate in self._filesystem_match_candidates(record):
                candidate_indexes.setdefault(candidate, []).append(index)

        matched_filesystem: set[int] = set()
        merged: list[ModelRecord] = []
        for api_record in api_records:
            api_key = self._normalize_identifier(api_record.identifier)
            candidates = [
                index
                for index in candidate_indexes.get(api_key, ())
                if index not in matched_filesystem
            ]
            if len(candidates) != 1:
                merged.append(api_record)
                continue

            index = candidates[0]
            matched_filesystem.add(index)
            filesystem_record = filesystem_records[index]
            metadata = dict(api_record.metadata)
            metadata.update(filesystem_record.metadata)
            metadata["source"] = "api+filesystem"
            merged.append(
                ModelRecord(
                    provider=self.name,
                    identifier=api_record.identifier,
                    name=api_record.name,
                    size_bytes=filesystem_record.size_bytes,
                    path=filesystem_record.path,
                    metadata=metadata,
                )
            )

        merged.extend(
            record
            for index, record in enumerate(filesystem_records)
            if index not in matched_filesystem
        )
        return tuple(merged)

    def _filesystem_match_candidates(
        self, record: ModelRecord
    ) -> set[str]:
        relative_path = record.metadata["relative_path"]
        candidates = {
            self._normalize_identifier(relative_path),
            self._normalize_identifier(Path(relative_path).name),
        }
        artifacts = record.metadata["artifacts"]
        for artifact in artifacts:
            artifact_path = Path(artifact["path"])
            if artifact_path.suffix.casefold() in _MODEL_FILE_SUFFIXES:
                candidates.add(
                    self._normalize_identifier(artifact_path.stem)
                )
        return candidates

    @staticmethod
    def _normalize_identifier(identifier: str) -> str:
        return identifier.strip().replace("\\", "/").strip("/").casefold()

    @staticmethod
    def _with_metadata(record: ModelRecord, **metadata: Any) -> ModelRecord:
        merged_metadata = dict(record.metadata)
        merged_metadata.update(metadata)
        return ModelRecord(
            provider=record.provider,
            identifier=record.identifier,
            name=record.name,
            size_bytes=record.size_bytes,
            path=record.path,
            metadata=merged_metadata,
        )

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
