"""Unified storage reporting and read-only cleanup candidate analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .errors import CheckerError
from .models import ModelRecord
from .providers import ProviderRegistry

SCHEMA_VERSION = 1
SAFETY_WARNING = (
    "Cleanup candidates are advisory only. Review resource dependencies and "
    "retention requirements before taking any action."
)
_DUPLICATE_SOURCES = frozenset(("api", "filesystem"))
_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class CleanupCandidate:
    """A reason that a record may merit manual cleanup review."""

    candidate: bool
    heuristic: bool
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "heuristic": self.heuristic,
            "reasons": list(self.reasons),
            "automatically_safe_to_delete": False,
        }


@dataclass(frozen=True, slots=True)
class AnalyzedRecord:
    """A raw provider record paired with cleanup assessment."""

    record: ModelRecord
    cleanup: CleanupCandidate

    @property
    def resource_type(self) -> str:
        value = self.record.metadata.get("resource_type", "model")
        return value if isinstance(value, str) and value else "model"

    def to_dict(self) -> dict[str, Any]:
        payload = self.record.to_dict()
        payload["resource_type"] = self.resource_type
        payload["cleanup_candidate"] = self.cleanup.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class StorageReport:
    """Stable report payload produced from all requested providers."""

    records: tuple[AnalyzedRecord, ...]
    summary: Mapping[str, Any]
    warnings: tuple[str, ...]
    errors: tuple[CheckerError, ...]
    providers_requested: tuple[str, ...]
    providers_succeeded: tuple[str, ...]
    filters: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "providers_requested": list(self.providers_requested),
            "providers_succeeded": list(self.providers_succeeded),
            "filters": dict(self.filters),
            "summary": dict(self.summary),
            "records": [record.to_dict() for record in self.records],
            "warnings": list(self.warnings),
            "errors": [error.to_dict() for error in self.errors],
        }


def human_size(size_bytes: int | None) -> str:
    """Format a byte count using deterministic IEC units."""

    if size_bytes is None:
        return "unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    value = float(size_bytes)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{size_bytes} B"
    return f"{value:.1f} {unit}"


def build_report(
    registry: ProviderRegistry,
    *,
    providers: Iterable[str] | None = None,
    resources: Iterable[str] | None = None,
    minimum_size: int = 0,
    largest_first: bool = False,
    candidates_only: bool = False,
) -> StorageReport:
    """Inventory providers independently and return a deterministic report."""

    requested = tuple(
        sorted(set(registry.names if providers is None else providers))
    )
    resource_filter = tuple(sorted(set(resources or ())))
    raw_records: list[ModelRecord] = []
    errors: list[CheckerError] = []
    succeeded: list[str] = []

    for provider in requested:
        result = registry.list_models(provider)
        if result.succeeded:
            succeeded.append(provider)
            assert result.value is not None
            raw_records.extend(result.value)
        else:
            errors.extend(result.errors)

    analyzed = _analyze_records(raw_records)
    selected = tuple(
        record
        for record in analyzed
        if (not resource_filter or record.resource_type in resource_filter)
        and (
            minimum_size == 0
            or (
                record.record.size_bytes is not None
                and record.record.size_bytes >= minimum_size
            )
        )
        and (not candidates_only or record.cleanup.candidate)
    )
    selected = tuple(sorted(selected, key=_record_sort_key(largest_first)))
    filters = {
        "providers": list(requested),
        "resources": list(resource_filter),
        "minimum_size_bytes": minimum_size,
        "candidates_only": candidates_only,
        "sort": "largest_first" if largest_first else "provider_resource_name",
    }
    return StorageReport(
        records=selected,
        summary=_summarize(selected),
        warnings=(SAFETY_WARNING, *_provider_warnings(raw_records)),
        errors=tuple(
            sorted(
                errors,
                key=lambda error: (
                    error.provider or "",
                    error.code.value,
                    error.message,
                ),
            )
        ),
        providers_requested=requested,
        providers_succeeded=tuple(sorted(succeeded)),
        filters=filters,
    )


def _provider_warnings(records: Iterable[ModelRecord]) -> tuple[str, ...]:
    warnings: set[str] = set()
    for record in records:
        if "api_unavailable" in record.metadata:
            warnings.add(
                f"{record.provider}: API unavailable; filesystem inventory "
                "was used."
            )
        missing_roots = record.metadata.get("missing_model_roots")
        if missing_roots:
            warnings.add(
                f"{record.provider}: one or more configured model "
                "directories are absent."
            )
    return tuple(sorted(warnings))


def _analyze_records(
    records: Iterable[ModelRecord],
) -> tuple[AnalyzedRecord, ...]:
    ordered = tuple(sorted(records, key=_raw_record_key))
    duplicate_groups: dict[tuple[str, str], list[int]] = {}
    for index, record in enumerate(ordered):
        if record.metadata.get("resource_type", "model") != "model":
            continue
        key = _duplicate_key(record)
        if key:
            duplicate_groups.setdefault((record.provider, key), []).append(
                index
            )

    duplicate_indexes: set[int] = set()
    for indexes in duplicate_groups.values():
        sources = {
            str(ordered[index].metadata.get("source", ""))
            for index in indexes
        }
        paths = {
            ordered[index].path
            for index in indexes
            if ordered[index].path is not None
        }
        if len(indexes) > 1 and (
            _DUPLICATE_SOURCES.issubset(sources) or len(paths) < len(indexes)
        ):
            duplicate_indexes.update(indexes)

    analyzed: list[AnalyzedRecord] = []
    for index, record in enumerate(ordered):
        reasons: list[str] = []
        heuristic = False
        resource_type = record.metadata.get("resource_type", "model")
        if (
            record.provider == "docker"
            and resource_type == "image"
            and record.metadata.get("dangling") is True
        ):
            reasons.append(
                "Docker reports the image as dangling; manual dependency "
                "review is still required."
            )
        if (
            record.provider == "docker"
            and resource_type == "container"
            and record.metadata.get("running") is False
        ):
            reasons.append(
                "Docker reports the container as stopped; retained data and "
                "restart requirements must be reviewed."
            )
        if index in duplicate_indexes:
            heuristic = True
            reasons.append(
                "Heuristic: another filesystem/API model record has the same "
                "normalized identity; verify both records before cleanup."
            )
        analyzed.append(
            AnalyzedRecord(
                record=record,
                cleanup=CleanupCandidate(
                    candidate=bool(reasons),
                    heuristic=heuristic,
                    reasons=tuple(reasons),
                ),
            )
        )
    return tuple(analyzed)


def _duplicate_key(record: ModelRecord) -> str:
    source = str(record.metadata.get("source", ""))
    if source not in _DUPLICATE_SOURCES:
        return ""
    value = record.name
    if source == "filesystem":
        value = str(record.metadata.get("relative_path", record.name))
        value = Path(value).name
    return _NORMALIZE_PATTERN.sub("", value.casefold())


def _raw_record_key(record: ModelRecord) -> tuple[Any, ...]:
    resource = str(record.metadata.get("resource_type", "model"))
    return (
        record.provider,
        resource,
        record.name.casefold(),
        record.identifier,
        record.path or "",
    )


def _record_sort_key(largest_first: bool):
    def key(record: AnalyzedRecord) -> tuple[Any, ...]:
        stable = (
            record.record.provider,
            record.resource_type,
            record.record.name.casefold(),
            record.record.identifier,
            record.record.path or "",
        )
        if not largest_first:
            return stable
        size = record.record.size_bytes
        return (-(size if size is not None else -1), *stable)

    return key


def _summarize(records: tuple[AnalyzedRecord, ...]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[AnalyzedRecord]] = {}
    for record in records:
        groups.setdefault(
            (record.record.provider, record.resource_type), []
        ).append(record)

    group_payloads: list[dict[str, Any]] = []
    for (provider, resource_type), group in sorted(groups.items()):
        known_sizes = [
            record.record.size_bytes
            for record in group
            if record.record.size_bytes is not None
        ]
        largest = sorted(
            group,
            key=lambda record: (
                -(record.record.size_bytes or 0),
                record.record.name.casefold(),
                record.record.identifier,
            ),
        )[:3]
        total = sum(known_sizes)
        group_payloads.append(
            {
                "provider": provider,
                "resource_type": resource_type,
                "item_count": len(group),
                "known_size_count": len(known_sizes),
                "total_bytes": total,
                "total_size": human_size(total),
                "cleanup_candidate_count": sum(
                    record.cleanup.candidate for record in group
                ),
                "largest_items": [
                    {
                        "identifier": record.record.identifier,
                        "name": record.record.name,
                        "size_bytes": record.record.size_bytes,
                        "size": human_size(record.record.size_bytes),
                    }
                    for record in largest
                ],
            }
        )

    known_sizes = [
        record.record.size_bytes
        for record in records
        if record.record.size_bytes is not None
    ]
    total = sum(known_sizes)
    return {
        "item_count": len(records),
        "known_size_count": len(known_sizes),
        "total_bytes": total,
        "total_size": human_size(total),
        "cleanup_candidate_count": sum(
            record.cleanup.candidate for record in records
        ),
        "groups": group_payloads,
    }
