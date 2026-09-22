"""Command-line interface for model storage checks."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO

from .errors import (
    ProviderFailureError,
    ProviderUnavailableError,
    UnsupportedOperationError,
    UnsupportedProviderError,
)
from .models import Operation, ProviderResult, ProviderStatus
from .providers import DEFAULT_REGISTRY, ProviderRegistry

EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3
EXIT_UNSUPPORTED = 4


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
    payload = {
        "operation": operation.value,
        "providers": [result.to_dict() for result in results],
        "version": 1,
    }
    json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
    stream.write("\n")


def _write_text(stream: TextIO, results: Sequence[ProviderResult]) -> None:
    for result in results:
        if result.status is ProviderStatus.OK:
            stream.write(f"{result.provider}: ok ({len(result.records)} models)\n")
            for record in result.records:
                size = (
                    f"{record.size_bytes} bytes"
                    if record.size_bytes is not None
                    else "size unknown"
                )
                stream.write(f"  {record.model_id} ({size})\n")
        else:
            stream.write(f"{result.provider}: {result.status.value} - {result.message}\n")


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
    provider_names = args.providers if args.providers is not None else registry.names
    results = collect_results(registry, provider_names, operation)

    if args.output == "json":
        _write_json(stream, operation, results)
    else:
        _write_text(stream, results)
    return _exit_code(results)
