"""Typed records shared by the command line and provider implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class Operation(StrEnum):
    LIST = "list"


class ProviderStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ModelRecord:
    provider: str
    model_id: str
    size_bytes: int | None = None
    location: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("provider must not be empty")
        if not self.model_id:
            raise ValueError("model_id must not be empty")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        normalized = dict(sorted(self.attributes.items()))
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in normalized.items()):
            raise TypeError("attribute keys and values must be strings")
        object.__setattr__(self, "attributes", MappingProxyType(normalized))

    def to_dict(self) -> dict[str, object]:
        return {
            "attributes": dict(self.attributes),
            "location": self.location,
            "model_id": self.model_id,
            "provider": self.provider,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider: str
    operation: Operation
    status: ProviderStatus
    records: tuple[ModelRecord, ...] = ()
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.provider:
            raise ValueError("provider must not be empty")
        if self.status is ProviderStatus.OK and self.message is not None:
            raise ValueError("successful results must not contain an error message")
        if self.status is not ProviderStatus.OK and not self.message:
            raise ValueError("unsuccessful results must contain an error message")
        if any(record.provider != self.provider for record in self.records):
            raise ValueError("record provider must match result provider")

    @classmethod
    def success(
        cls,
        provider: str,
        operation: Operation,
        records: tuple[ModelRecord, ...] = (),
    ) -> ProviderResult:
        ordered = tuple(
            sorted(records, key=lambda record: (record.model_id, record.location or ""))
        )
        return cls(provider, operation, ProviderStatus.OK, ordered)

    @classmethod
    def failure(
        cls,
        provider: str,
        operation: Operation,
        status: ProviderStatus,
        message: str,
        records: tuple[ModelRecord, ...] = (),
    ) -> ProviderResult:
        if status is ProviderStatus.OK:
            raise ValueError("failure status must not be ok")
        ordered = tuple(
            sorted(records, key=lambda record: (record.model_id, record.location or ""))
        )
        return cls(provider, operation, status, ordered, message)

    def to_dict(self) -> dict[str, object]:
        return {
            "message": self.message,
            "operation": self.operation.value,
            "provider": self.provider,
            "records": [record.to_dict() for record in self.records],
            "status": self.status.value,
        }
