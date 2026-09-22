"""Argument parsing and output formatting."""

from __future__ import annotations

import argparse
import json
import sys
from enum import IntEnum
from typing import Sequence, TextIO

from . import __version__
from .errors import CheckerError
from .models import ModelRecord
from .providers import ProviderRegistry, ProviderStatus


class ExitCode(IntEnum):
    SUCCESS = 0
    FAILURE = 1
    USAGE = 2
    UNAVAILABLE = 3


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


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    registry: ProviderRegistry | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    active_registry = registry if registry is not None else ProviderRegistry()

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

    raise AssertionError(f"unhandled command: {args.command}")
