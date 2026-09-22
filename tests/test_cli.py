import io
import json
import unittest

from model_storage_checker.cli import (
    EXIT_UNAVAILABLE,
    EXIT_UNSUPPORTED,
    main,
)
from model_storage_checker.errors import (
    ProviderUnavailableError,
    UnsupportedOperationError,
)
from model_storage_checker.models import ModelRecord, Operation, ProviderResult
from model_storage_checker.providers import ProviderRegistry


class SuccessfulProvider:
    name = "working"

    def run(self, operation: Operation) -> ProviderResult:
        return ProviderResult.success(
            self.name,
            operation,
            (
                ModelRecord(provider=self.name, model_id="z", size_bytes=20),
                ModelRecord(provider=self.name, model_id="a"),
            ),
        )


class UnavailableProvider:
    name = "offline"

    def run(self, operation: Operation) -> ProviderResult:
        raise ProviderUnavailableError(self.name, "service is not running")


class WrongOperationProvider:
    name = "limited"

    def run(self, operation: Operation) -> ProviderResult:
        raise UnsupportedOperationError(self.name, operation.value)


class CliTests(unittest.TestCase):
    def test_default_text_reports_unsupported_providers(self) -> None:
        stream = io.StringIO()

        exit_code = main(["list"], stdout=stream)

        self.assertEqual(exit_code, EXIT_UNSUPPORTED)
        self.assertEqual(
            stream.getvalue(),
            "docker: unsupported - Provider 'docker' is not supported\n"
            "lm-studio: unsupported - Provider 'lm-studio' is not supported\n"
            "ollama: unsupported - Provider 'ollama' is not supported\n",
        )

    def test_json_is_deterministic(self) -> None:
        registry = ProviderRegistry(
            (SuccessfulProvider(),), unsupported_names=("planned",)
        )
        first = io.StringIO()
        second = io.StringIO()
        args = [
            "list",
            "--provider",
            "working",
            "--provider",
            "planned",
            "--output",
            "json",
        ]

        first_exit = main(args, registry=registry, stdout=first)
        second_exit = main(args, registry=registry, stdout=second)

        self.assertEqual(first_exit, EXIT_UNSUPPORTED)
        self.assertEqual(first.getvalue(), second.getvalue())
        payload = json.loads(first.getvalue())
        self.assertEqual(
            [provider["provider"] for provider in payload["providers"]],
            ["planned", "working"],
        )
        self.assertEqual(
            [record["model_id"] for record in payload["providers"][1]["records"]],
            ["a", "z"],
        )

    def test_unavailable_provider_has_explicit_status_and_exit_code(self) -> None:
        registry = ProviderRegistry((UnavailableProvider(),))
        stream = io.StringIO()

        exit_code = main(
            ["list", "--output", "json"], registry=registry, stdout=stream
        )

        self.assertEqual(exit_code, EXIT_UNAVAILABLE)
        self.assertEqual(
            json.loads(stream.getvalue())["providers"][0]["status"], "unavailable"
        )

    def test_unsupported_operation_from_provider_is_reported(self) -> None:
        registry = ProviderRegistry((WrongOperationProvider(),))
        stream = io.StringIO()

        exit_code = main(["list"], registry=registry, stdout=stream)

        self.assertEqual(exit_code, EXIT_UNSUPPORTED)
        self.assertIn("does not support operation 'list'", stream.getvalue())

    def test_argparse_rejects_unknown_operation_and_provider(self) -> None:
        for args in (["delete"], ["list", "--provider", "unknown"]):
            with self.subTest(args=args):
                with self.assertRaises(SystemExit) as context:
                    main(args)
                self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
