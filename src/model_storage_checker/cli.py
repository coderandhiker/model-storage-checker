"""Argument parsing and output formatting."""

from __future__ import annotations

import argparse
import json
import math
import sys
from enum import IntEnum
from typing import Sequence, TextIO

from . import __version__
from .docker import (
    DEFAULT_EXECUTABLE as DOCKER_DEFAULT_EXECUTABLE,
    DEFAULT_TIMEOUT as DOCKER_DEFAULT_TIMEOUT,
    DockerProvider,
)
from .errors import CheckerError
from .lm_studio import (
    DEFAULT_BASE_URL as LM_STUDIO_DEFAULT_BASE_URL,
    DEFAULT_MODEL_ROOTS as LM_STUDIO_DEFAULT_MODEL_ROOTS,
    DEFAULT_TIMEOUT as LM_STUDIO_DEFAULT_TIMEOUT,
    LMStudioProvider,
)
from .models import ModelRecord
from .ollama import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, OllamaProvider
from .providers import ProviderRegistry, ProviderStatus
from .reporting import StorageReport, build_report, human_size


class ExitCode(IntEnum):
    SUCCESS = 0
    FAILURE = 1
    USAGE = 2
    UNAVAILABLE = 3


def _positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("timeout must be a number") from error
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be positive")
    return timeout


def _nonnegative_size(value: str) -> int:
    try:
        size = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "minimum size must be an integer number of bytes"
        ) from error
    if size < 0:
        raise argparse.ArgumentTypeError("minimum size must not be negative")
    return size


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model-storage-checker",
        description="Inspect model artifacts exposed by registered providers.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="select output format (default: text)",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_BASE_URL,
        help=f"Ollama API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--ollama-timeout",
        default=DEFAULT_TIMEOUT,
        type=_positive_timeout,
        metavar="SECONDS",
        help=f"Ollama request timeout (default: {DEFAULT_TIMEOUT:g} seconds)",
    )
    parser.add_argument(
        "--lm-studio-base-url",
        default=LM_STUDIO_DEFAULT_BASE_URL,
        help=(
            "LM Studio API base URL "
            f"(default: {LM_STUDIO_DEFAULT_BASE_URL})"
        ),
    )
    parser.add_argument(
        "--lm-studio-timeout",
        default=LM_STUDIO_DEFAULT_TIMEOUT,
        type=_positive_timeout,
        metavar="SECONDS",
        help=(
            "LM Studio request timeout "
            f"(default: {LM_STUDIO_DEFAULT_TIMEOUT:g} seconds)"
        ),
    )
    parser.add_argument(
        "--lm-studio-model-root",
        action="append",
        dest="lm_studio_model_roots",
        metavar="PATH",
        help=(
            "LM Studio model directory; repeat for multiple roots "
            f"(default: {LM_STUDIO_DEFAULT_MODEL_ROOTS[0]})"
        ),
    )
    parser.add_argument(
        "--docker-executable",
        default=DOCKER_DEFAULT_EXECUTABLE,
        metavar="PATH",
        help=(
            "Docker CLI executable "
            f"(default: {DOCKER_DEFAULT_EXECUTABLE})"
        ),
    )
    parser.add_argument(
        "--docker-timeout",
        default=DOCKER_DEFAULT_TIMEOUT,
        type=_positive_timeout,
        metavar="SECONDS",
        help=(
            "Docker command timeout "
            f"(default: {DOCKER_DEFAULT_TIMEOUT:g} seconds)"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "providers", help="show registered providers and their availability"
    )
    list_parser = subparsers.add_parser(
        "list", help="list model artifacts from a provider"
    )
    list_parser.add_argument(
        "--provider", required=True, help="registered provider name"
    )
    report_parser = subparsers.add_parser(
        "report",
        help="inventory providers and summarize storage and cleanup candidates",
    )
    report_parser.add_argument(
        "--provider",
        action="append",
        dest="providers",
        metavar="NAME",
        help="include a provider; repeat to include multiple (default: all)",
    )
    report_parser.add_argument(
        "--resource",
        action="append",
        dest="resources",
        metavar="TYPE",
        help="include a resource type; repeat for multiple types",
    )
    report_parser.add_argument(
        "--min-size",
        default=0,
        type=_nonnegative_size,
        metavar="BYTES",
        help="include records at least this many bytes (default: 0)",
    )
    report_parser.add_argument(
        "--largest-first",
        action="store_true",
        help="sort records by descending size",
    )
    report_parser.add_argument(
        "--candidates-only",
        action="store_true",
        help="include only records flagged for manual cleanup review",
    )
    return parser


def _write_json(payload: object, stream: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True), file=stream)


def _write_errors(
    errors: tuple[CheckerError, ...], output: str, stream: TextIO
) -> None:
    if output == "json":
        _write_json({"errors": [error.to_dict() for error in errors]}, stream)
        return
    for error in errors:
        provider = f" [{error.provider}]" if error.provider else ""
        print(f"error: {error.code.value}{provider}: {error.message}", file=stream)


def _write_statuses(
    statuses: tuple[ProviderStatus, ...], output: str, stream: TextIO
) -> None:
    if output == "json":
        _write_json(
            {"providers": [status.to_dict() for status in statuses]}, stream
        )
        return
    if not statuses:
        print("No providers are registered.", file=stream)
        return
    for status in statuses:
        state = "available" if status.available else "unavailable"
        suffix = f": {status.message}" if status.message else ""
        print(f"{status.name}: {state}{suffix}", file=stream)


def _write_models(
    models: tuple[ModelRecord, ...], output: str, stream: TextIO
) -> None:
    if output == "json":
        _write_json({"models": [model.to_dict() for model in models]}, stream)
        return
    if not models:
        print("No models found.", file=stream)
        return
    for model in models:
        size = (
            f" ({model.size_bytes} bytes)"
            if model.size_bytes is not None
            else ""
        )
        print(f"{model.provider}: {model.name} [{model.identifier}]{size}", file=stream)


def _write_report(
    report: StorageReport, output: str, stream: TextIO
) -> None:
    if output == "json":
        _write_json(report.to_dict(), stream)
        return

    summary = report.summary
    print(
        "Storage summary: "
        f"{summary['item_count']} items, "
        f"{summary['total_size']} ({summary['total_bytes']} bytes), "
        f"{summary['cleanup_candidate_count']} cleanup candidates",
        file=stream,
    )
    groups = summary["groups"]
    if not groups:
        print("No records matched the selected filters.", file=stream)
    for group in groups:
        print(
            f"{group['provider']} / {group['resource_type']}: "
            f"{group['item_count']} items, {group['total_size']} "
            f"({group['total_bytes']} bytes), "
            f"{group['cleanup_candidate_count']} candidates",
            file=stream,
        )
        for item in group["largest_items"]:
            print(
                f"  largest: {item['name']} [{item['identifier']}] "
                f"{item['size']} "
                f"({item['size_bytes'] if item['size_bytes'] is not None else 'unknown'}"
                " bytes)",
                file=stream,
            )
    candidates = [record for record in report.records if record.cleanup.candidate]
    if candidates:
        print("Cleanup candidates (manual review required):", file=stream)
        for record in candidates:
            print(
                f"  {record.record.provider}/{record.resource_type}: "
                f"{record.record.name} ({human_size(record.record.size_bytes)})",
                file=stream,
            )
            for reason in record.cleanup.reasons:
                print(f"    - {reason}", file=stream)
    for warning in report.warnings:
        print(f"warning: {warning}", file=stream)
    for error in report.errors:
        provider = f" [{error.provider}]" if error.provider else ""
        print(
            f"error: {error.code.value}{provider}: {error.message}",
            file=stream,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    registry: ProviderRegistry | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    active_registry = (
        registry
        if registry is not None
        else ProviderRegistry(
            (
                OllamaProvider(
                    base_url=args.ollama_base_url,
                    timeout=args.ollama_timeout,
                ),
                LMStudioProvider(
                    base_url=args.lm_studio_base_url,
                    timeout=args.lm_studio_timeout,
                    model_roots=args.lm_studio_model_roots,
                ),
                DockerProvider(
                    executable=args.docker_executable,
                    timeout=args.docker_timeout,
                ),
            )
        )
    )

    if args.command == "providers":
        _write_statuses(active_registry.statuses(), args.output, stdout)
        return ExitCode.SUCCESS

    if args.command == "list":
        result = active_registry.list_models(args.provider)
        if not result.succeeded:
            _write_errors(result.errors, args.output, stderr)
            if all(
                error.code.value == "provider_unavailable"
                for error in result.errors
            ):
                return ExitCode.UNAVAILABLE
            return ExitCode.FAILURE
        assert result.value is not None
        _write_models(result.value, args.output, stdout)
        return ExitCode.SUCCESS

    if args.command == "report":
        report = build_report(
            active_registry,
            providers=args.providers,
            resources=args.resources,
            minimum_size=args.min_size,
            largest_first=args.largest_first,
            candidates_only=args.candidates_only,
        )
        _write_report(report, args.output, stdout)
        if report.providers_succeeded:
            return ExitCode.SUCCESS
        if report.errors and all(
            error.code.value == "provider_unavailable"
            for error in report.errors
        ):
            return ExitCode.UNAVAILABLE
        return ExitCode.FAILURE

    raise AssertionError(f"unhandled command: {args.command}")
