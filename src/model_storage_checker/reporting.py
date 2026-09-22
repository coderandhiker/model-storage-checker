"""Deterministic unified summaries and advisory cleanup candidates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from .models import ModelRecord, ProviderResult


@dataclass(frozen=True, slots=True)
class StorageTotal:
    record_count: int
    known_size_count: int
    unknown_size_count: int
    known_size_bytes: int

    @property
    def total_size_bytes(self) -> int | None:
        if self.unknown_size_count:
            return None
        return self.known_size_bytes

    def to_dict(self) -> dict[str, int | None]:
        return {
            "known_size_bytes": self.known_size_bytes,
            "known_size_count": self.known_size_count,
            "record_count": self.record_count,
            "total_size_bytes": self.total_size_bytes,
            "unknown_size_count": self.unknown_size_count,
        }


@dataclass(frozen=True, slots=True)
class CleanupCandidate:
    provider: str
    resource_type: str
    record_id: str
    rule: str
    rationale: str
    evidence: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evidence", MappingProxyType(dict(sorted(self.evidence.items())))
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "advisory_only": True,
            "classification": "heuristic",
            "evidence": dict(self.evidence),
            "evidence_kind": "reported_metadata",
            "provider": self.provider,
            "rationale": self.rationale,
            "record_id": self.record_id,
            "resource_type": self.resource_type,
            "rule": self.rule,
        }


@dataclass(frozen=True, slots=True)
class StorageSummary:
    total: StorageTotal
    by_provider: Mapping[str, StorageTotal]
    by_resource_type: Mapping[str, StorageTotal]
    by_provider_and_resource_type: Mapping[str, Mapping[str, StorageTotal]]

    def to_dict(self) -> dict[str, object]:
        return {
            "by_provider": {
                provider: total.to_dict()
                for provider, total in self.by_provider.items()
            },
            "by_provider_and_resource_type": {
                provider: {
                    resource_type: total.to_dict()
                    for resource_type, total in resource_totals.items()
                }
                for provider, resource_totals in (
                    self.by_provider_and_resource_type.items()
                )
            },
            "by_resource_type": {
                resource_type: total.to_dict()
                for resource_type, total in self.by_resource_type.items()
            },
            "total": self.total.to_dict(),
        }


def resource_type(record: ModelRecord) -> str:
    kind = record.attributes.get("inventory.kind")
    if record.provider == "docker" and kind in {"container", "image"}:
        return kind
    return "model"


def build_summary(results: Sequence[ProviderResult]) -> StorageSummary:
    records = tuple(record for result in results for record in result.records)
    provider_names = sorted({result.provider for result in results})
    resource_types = sorted({resource_type(record) for record in records})

    by_provider = {
        provider: _total(record for record in records if record.provider == provider)
        for provider in provider_names
    }
    by_resource_type = {
        kind: _total(record for record in records if resource_type(record) == kind)
        for kind in resource_types
    }
    by_provider_and_resource_type = {
        provider: MappingProxyType(
            {
                kind: _total(
                    record
                    for record in records
                    if record.provider == provider and resource_type(record) == kind
                )
                for kind in sorted(
                    {
                        resource_type(record)
                        for record in records
                        if record.provider == provider
                    }
                )
            }
        )
        for provider in provider_names
    }
    return StorageSummary(
        total=_total(iter(records)),
        by_provider=MappingProxyType(by_provider),
        by_resource_type=MappingProxyType(by_resource_type),
        by_provider_and_resource_type=MappingProxyType(
            by_provider_and_resource_type
        ),
    )


def find_cleanup_candidates(
    results: Sequence[ProviderResult],
) -> tuple[CleanupCandidate, ...]:
    candidates: list[CleanupCandidate] = []
    for result in results:
        for record in result.records:
            kind = resource_type(record)
            if record.provider != "docker":
                continue
            if (
                kind == "image"
                and record.attributes.get("docker.Repository") == "<none>"
                and record.attributes.get("docker.Tag") == "<none>"
            ):
                candidates.append(
                    CleanupCandidate(
                        provider="docker",
                        resource_type="image",
                        record_id=record.model_id,
                        rule="docker-image-untagged",
                        rationale=(
                            "Repository and tag are both reported as <none>; "
                            "review whether the image is still needed. This does "
                            "not prove that removal is safe."
                        ),
                        evidence={
                            "docker.Repository": "<none>",
                            "docker.Tag": "<none>",
                        },
                    )
                )
            elif (
                kind == "container"
                and record.attributes.get("docker.State", "").lower()
                in {"dead", "exited"}
            ):
                state = record.attributes["docker.State"]
                candidates.append(
                    CleanupCandidate(
                        provider="docker",
                        resource_type="container",
                        record_id=record.model_id,
                        rule="docker-container-not-running",
                        rationale=(
                            "State is reported as exited or dead; review whether "
                            "the container is still needed. State alone does not "
                            "prove that removal is safe."
                        ),
                        evidence={"docker.State": state},
                    )
                )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.provider,
                item.resource_type,
                item.record_id,
                item.rule,
            ),
        )
    )


def _total(records: Iterable[ModelRecord]) -> StorageTotal:
    materialized = tuple(records)
    known_sizes = tuple(
        record.size_bytes
        for record in materialized
        if record.size_bytes is not None
    )
    return StorageTotal(
        record_count=len(materialized),
        known_size_count=len(known_sizes),
        unknown_size_count=len(materialized) - len(known_sizes),
        known_size_bytes=sum(known_sizes),
    )
