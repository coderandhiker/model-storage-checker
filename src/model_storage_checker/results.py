"""Typed operation results for expected provider outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from .errors import CheckerError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class OperationResult(Generic[T]):
    """A value or one or more explicit expected errors."""

    value: T | None
    errors: tuple[CheckerError, ...] = ()

    def __post_init__(self) -> None:
        if (self.value is None) == (not self.errors):
            raise ValueError("result must contain either a value or errors")

    @property
    def succeeded(self) -> bool:
        return not self.errors

    @classmethod
    def success(cls, value: T) -> OperationResult[T]:
        return cls(value=value)

    @classmethod
    def failure(
        cls, error: CheckerError, *additional_errors: CheckerError
    ) -> OperationResult[T]:
        return cls(value=None, errors=(error, *additional_errors))
