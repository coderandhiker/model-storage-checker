"""Command-line interface for model storage checks."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from typing import TextIO

from .docker import DEFAULT_TIMEOUT as DEFAULT_DOCKER_TIMEOUT
from .errors import (
    ProviderFailureError,
    ProviderUnavailableError,
    UnsupportedOperationError,
    UnsupportedProviderError,
)
from .lm_studio import (
    DEFAULT_BASE_URL as DEFAULT_LM_STUDIO_BASE_URL,
    DEFAULT_MODEL_ROOTS,
    DEFAULT_TIMEOUT as DEFAULT_LM_STUDIO_TIMEOUT,
    LMStudioConfig,
)
from .models import Operation, ProviderResult, ProviderStatus
from .ollama import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, OllamaConfig
from .providers import DEFAULT_REGISTRY, ProviderRegistry, create_default_registry
from .reporting import StorageTotal, build_summary, find_cleanup_candidates

EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3
EXIT_UNSUPPORTED = 4


def _positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError(
            "must be a finite number greater than zero"
        )
    return timeout


def _ollama_base_url(value: str) -> str:
    try:
        return OllamaConfig(base_url=value).base_url
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _lm_studio_base_url(value: str) -> str:
    try:
        return LMStudioConfig(base_url=value).base_url
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def build_parser(registry: ProviderRegistry = DEFAULT_REGISTRY) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model-storage-checker",
        description="Report locally stored models from read-only providers.",
    )
    parser.add_argument(
        "operation",
        choices=tuple(operation.value for operation in Operation),
        help="read-only operation to perform",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=registry.names,
        dest="providers",
        help="provider to check; repeat to select multiple (default: all)",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_BASE_URL,
        type=_ollama_base_url,
        help=f"Ollama service base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--ollama-timeout",
        default=DEFAULT_TIMEOUT,
        type=_positive_timeout,
        metavar="SECONDS",
        help=f"Ollama request timeout in seconds (default: {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument(
        "--lm-studio-base-url",
        default=DEFAULT_LM_STUDIO_BASE_URL,
        type=_lm_studio_base_url,
        help=(
            "LM Studio OpenAI-compatible base URL "
            f"(default: {DEFAULT_LM_STUDIO_BASE_URL})"
        ),
    )
    parser.add_argument(
        "--lm-studio-timeout",
        default=DEFAULT_LM_STUDIO_TIMEOUT,
        type=_positive_timeout,
        metavar="SECONDS",
        help=(
            "LM Studio request timeout in seconds "
            f"(default: {DEFAULT_LM_STUDIO_TIMEOUT:g})"
        ),
    )
    parser.add_argument(
        "--lm-studio-model-root",
        action="append",
        dest="lm_studio_model_roots",
        metavar="PATH",
        help=(
            "LM Studio model root to scan recursively; repeat for multiple roots "
            f"(default: {DEFAULT_MODEL_ROOTS[0]})"
        ),
    )
    parser.add_argument(
        "--docker-timeout",
        default=DEFAULT_DOCKER_TIMEOUT,
        type=_positive_timeout,
        metavar="SECONDS",
        help=(
            "Docker CLI timeout per inventory command in seconds "
            f"(default: {DEFAULT_DOCKER_TIMEOUT:g})"
        ),
    )
    parser.add_argument(
        "--docker-ai-heuristic",
        action="store_true",
        help="annotate Docker records with an optional AI-related heuristic",
    )
    return parser


def _failure_result(
    provider: str, operation: Operation, error: Exception
) -> ProviderResult:
    if isinstance(error, ProviderUnavailableError):
        status = ProviderStatus.UNAVAILABLE
    elif isinstance(error, (UnsupportedProviderError, UnsupportedOperationError)):
        status = ProviderStatus.UNSUPPORTED
    else:
        status = ProviderStatus.ERROR
    return ProviderResult.failure(provider, operation, status, str(error))


def collect_results(
    registry: ProviderRegistry,
    provider_names: Sequence[str],
    operation: Operation,
) -> tuple[ProviderResult, ...]:
    results: list[ProviderResult] = []
    for provider_name in sorted(set(provider_names)):
        try:
            result = registry.run(provider_name, operation)
        except (
            ProviderFailureError,
            ProviderUnavailableError,
            UnsupportedOperationError,
            UnsupportedProviderError,
        ) as error:
            result = _failure_result(provider_name, operation, error)
        results.append(result)
    return tuple(results)


def _write_json(
    stream: TextIO, operation: Operation, results: Sequence[ProviderResult]
) -> None:
    summary = build_summary(results)
    candidates = find_cleanup_candidates(results)
    payload = {
        "cleanup_candidates": [candidate.to_dict() for candidate in candidates],
        "operation": operation.value,
        "providers": [result.to_dict() for result in results],
        "storage_summary": summary.to_dict(),
        "version": 2,
    }
    json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
    stream.write("\n")


def _write_text(
    stream: TextIO,
    results: Sequence[ProviderResult],
    *,
    include_unified_summary: bool,
) -> None:
    for result in results:
        if result.status is ProviderStatus.OK:
            noun = "inventory records" if result.provider == "docker" else "models"
            stream.write(f"{result.provider}: ok ({len(result.records)} {noun})\n")
        else:
            noun = "inventory records" if result.provider == "docker" else "models"
            count = f" ({len(result.records)} {noun})" if result.records else ""
            stream.write(
                f"{result.provider}: {result.status.value}{count} - {result.message}\n"
            )
        for record in result.records:
            size = (
                f"{record.size_bytes} bytes"
                if record.size_bytes is not None
                else "size unknown"
            )
            stream.write(f"  {record.model_id} ({size})\n")

    if not include_unified_summary:
        return

    summary = build_summary(results)
    stream.write("storage summary:\n")
    stream.write(f"  all: {_format_total(summary.total)}\n")
    for provider, total in summary.by_provider.items():
        stream.write(f"  provider {provider}: {_format_total(total)}\n")
        for resource_type, resource_total in (
            summary.by_provider_and_resource_type[provider].items()
        ):
            stream.write(
                f"    {resource_type}: {_format_total(resource_total)}\n"
            )

    candidates = find_cleanup_candidates(results)
    stream.write(f"cleanup candidates (advisory only): {len(candidates)}\n")
    for candidate in candidates:
        evidence = ", ".join(
            f"{key}={value}" for key, value in candidate.evidence.items()
        )
        stream.write(
            f"  {candidate.provider}/{candidate.resource_type}/"
            f"{candidate.record_id}: heuristic {candidate.rule}\n"
            f"    evidence (reported metadata): {evidence}\n"
            f"    advisory: {candidate.rationale}\n"
        )


def _format_total(total: StorageTotal) -> str:
    known_size_bytes = total.known_size_bytes
    unknown_size_count = total.unknown_size_count
    record_count = total.record_count
    if unknown_size_count:
        size = (
            f"{known_size_bytes} known bytes; "
            f"{unknown_size_count} record(s) have unknown size"
        )
    else:
        size = f"{known_size_bytes} bytes"
    return f"{record_count} record(s), {size}"


def _exit_code(results: Sequence[ProviderResult]) -> int:
    statuses = {result.status for result in results}
    if ProviderStatus.ERROR in statuses:
        return EXIT_ERROR
    if ProviderStatus.UNSUPPORTED in statuses:
        return EXIT_UNSUPPORTED
    if ProviderStatus.UNAVAILABLE in statuses:
        return EXIT_UNAVAILABLE
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    registry: ProviderRegistry = DEFAULT_REGISTRY,
    stdout: TextIO | None = None,
) -> int:
    args = build_parser(registry).parse_args(argv)
    stream = stdout if stdout is not None else sys.stdout
    operation = Operation(args.operation)
    active_registry = registry
    if registry is DEFAULT_REGISTRY:
        active_registry = create_default_registry(
            ollama_base_url=args.ollama_base_url,
            ollama_timeout=args.ollama_timeout,
            lm_studio_base_url=args.lm_studio_base_url,
            lm_studio_timeout=args.lm_studio_timeout,
            lm_studio_model_roots=(
                tuple(args.lm_studio_model_roots)
                if args.lm_studio_model_roots is not None
                else None
            ),
            docker_timeout=args.docker_timeout,
            docker_classify_ai=args.docker_ai_heuristic,
        )
    provider_names = (
        args.providers if args.providers is not None else active_registry.names
    )
    results = collect_results(active_registry, provider_names, operation)

    if args.output == "json":
        _write_json(stream, operation, results)
    else:
        _write_text(
            stream,
            results,
            include_unified_summary=(
                args.providers is None and len(results) > 1
            ),
        )
    return _exit_code(results)
