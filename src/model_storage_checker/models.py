"""Core model records independent of any provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ModelRecord:
    """A model artifact discovered by a storage provider."""

    provider: str
    identifier: str
    name: str
    size_bytes: int | None = None
    path: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("provider", "identifier", "name"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "identifier": self.identifier,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "path": self.path,
            "metadata": dict(self.metadata),
        }
