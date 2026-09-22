"""Structured errors exposed by providers and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class ErrorCode(StrEnum):
    """Stable error codes suitable for machine-readable output."""

    INVALID_REQUEST = "invalid_request"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True, slots=True)
class CheckerError(Exception):
    """An expected failure with a stable code and useful context."""

    code: ErrorCode
    message: str
    provider: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.provider is not None:
            result["provider"] = self.provider
        if self.details:
            result["details"] = dict(self.details)
        return result
