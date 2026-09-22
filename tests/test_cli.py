import io
import json
import unittest
from unittest.mock import patch

from model_storage_checker.cli import (
    EXIT_ERROR,
    EXIT_UNAVAILABLE,
    EXIT_UNSUPPORTED,
    main,
)
from model_storage_checker.errors import (
    ProviderUnavailableError,
    UnsupportedOperationError,
)
from model_storage_checker.models import (
    ModelRecord,
    Operation,
    ProviderResult,
    ProviderStatus,
)
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


class SuccessfulOllamaProvider(SuccessfulProvider):
    name = "ollama"


class SuccessfulLMStudioProvider(SuccessfulProvider):
    name = "lm-studio"


class SuccessfulDockerProvider(SuccessfulProvider):
    name = "docker"


class UnavailableProvider:
    name = "offline"

    def run(self, operation: Operation) -> ProviderResult:
        raise ProviderUnavailableError(self.name, "service is not running")


class WrongOperationProvider:
    name = "limited"

    def run(self, operation: Operation) -> ProviderResult:
        raise UnsupportedOperationError(self.name, operation.value)


class PartialProvider:
    name = "partial"

    def run(self, operation: Operation) -> ProviderResult:
        return ProviderResult.failure(
            self.name,
            operation,
            ProviderStatus.ERROR,
            "one discovery source failed",
            (ModelRecord(self.name, "retained", 12),),
        )


class CliTests(unittest.TestCase):
    def test_default_text_reports_unsupported_providers(self) -> None:
        registry = ProviderRegistry(
            unsupported_names=("docker", "lm-studio", "ollama")
        )
        stream = io.StringIO()

        exit_code = main(["list"], registry=registry, stdout=stream)

        self.assertEqual(exit_code, EXIT_UNSUPPORTED)
        self.assertEqual(
            stream.getvalue(),
            "docker: unsupported - Provider 'docker' is not supported\n"
            "lm-studio: unsupported - Provider 'lm-studio' is not supported\n"
            "ollama: unsupported - Provider 'ollama' is not supported\n"
            "storage summary:\n"
            "  all: 0 record(s), 0 bytes\n"
            "  provider docker: 0 record(s), 0 bytes\n"
            "  provider lm-studio: 0 record(s), 0 bytes\n"
            "  provider ollama: 0 record(s), 0 bytes\n"
            "cleanup candidates (advisory only): 0\n",
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
        self.assertEqual(payload["version"], 2)
        self.assertIsNone(
            payload["storage_summary"]["total"]["total_size_bytes"]
        )
        self.assertEqual(
            payload["storage_summary"]["total"]["known_size_bytes"], 20
        )
        self.assertEqual(payload["cleanup_candidates"], [])

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

    def test_json_preserves_partial_failure_and_records(self) -> None:
        registry = ProviderRegistry((PartialProvider(),))
        stream = io.StringIO()

        exit_code = main(
            ["list", "--output", "json"], registry=registry, stdout=stream
        )

        payload = json.loads(stream.getvalue())
        self.assertEqual(exit_code, EXIT_ERROR)
        self.assertEqual(payload["providers"][0]["status"], "error")
        self.assertEqual(
            payload["providers"][0]["message"], "one discovery source failed"
        )
        self.assertEqual(
            payload["providers"][0]["records"][0]["model_id"], "retained"
        )
        self.assertEqual(
            payload["storage_summary"]["total"]["total_size_bytes"], 12
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

    def test_argparse_rejects_non_positive_ollama_timeout(self) -> None:
        for timeout in ("0", "-1", "nan", "inf", "not-a-number"):
            with self.subTest(timeout=timeout):
                with self.assertRaises(SystemExit) as context:
                    main(["list", "--ollama-timeout", timeout])
                self.assertEqual(context.exception.code, 2)

    def test_argparse_rejects_non_positive_docker_timeout(self) -> None:
        for timeout in ("0", "-1", "nan", "inf", "not-a-number"):
            with self.subTest(timeout=timeout):
                with self.assertRaises(SystemExit) as context:
                    main(["list", "--docker-timeout", timeout])
                self.assertEqual(context.exception.code, 2)

    def test_argparse_rejects_invalid_ollama_base_url(self) -> None:
        with self.assertRaises(SystemExit) as context:
            main(["list", "--ollama-base-url", "file:///tmp/ollama"])

        self.assertEqual(context.exception.code, 2)

    def test_ollama_options_configure_default_registry(self) -> None:
        configured_registry = ProviderRegistry((SuccessfulOllamaProvider(),))
        stream = io.StringIO()

        with patch(
            "model_storage_checker.cli.create_default_registry",
            return_value=configured_registry,
        ) as create_registry:
            exit_code = main(
                [
                    "list",
                    "--provider",
                    "ollama",
                    "--ollama-base-url",
                    "http://localhost:9999/",
                    "--ollama-timeout",
                    "1.25",
                ],
                stdout=stream,
            )

        self.assertEqual(exit_code, 0)
        create_registry.assert_called_once_with(
            ollama_base_url="http://localhost:9999",
            ollama_timeout=1.25,
            lm_studio_base_url="http://127.0.0.1:1234/v1",
            lm_studio_timeout=5.0,
            lm_studio_model_roots=None,
            docker_timeout=10.0,
            docker_classify_ai=False,
        )

    def test_lm_studio_options_configure_default_registry(self) -> None:
        configured_registry = ProviderRegistry((SuccessfulLMStudioProvider(),))
        stream = io.StringIO()

        with patch(
            "model_storage_checker.cli.create_default_registry",
            return_value=configured_registry,
        ) as create_registry:
            exit_code = main(
                [
                    "list",
                    "--provider",
                    "lm-studio",
                    "--lm-studio-base-url",
                    "http://localhost:9999/v1/",
                    "--lm-studio-timeout",
                    "2.5",
                    "--lm-studio-model-root",
                    "/models/one",
                    "--lm-studio-model-root",
                    "/models/two",
                ],
                stdout=stream,
            )

        self.assertEqual(exit_code, 0)
        create_registry.assert_called_once_with(
            ollama_base_url="http://127.0.0.1:11434",
            ollama_timeout=5.0,
            lm_studio_base_url="http://localhost:9999/v1",
            lm_studio_timeout=2.5,
            lm_studio_model_roots=("/models/one", "/models/two"),
            docker_timeout=10.0,
            docker_classify_ai=False,
        )

    def test_docker_options_configure_default_registry(self) -> None:
        configured_registry = ProviderRegistry((SuccessfulDockerProvider(),))
        stream = io.StringIO()

        with patch(
            "model_storage_checker.cli.create_default_registry",
            return_value=configured_registry,
        ) as create_registry:
            exit_code = main(
                [
                    "list",
                    "--provider",
                    "docker",
                    "--docker-timeout",
                    "4.5",
                    "--docker-ai-heuristic",
                ],
                stdout=stream,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stream.getvalue(),
            "docker: ok (2 inventory records)\n"
            "  a (size unknown)\n"
            "  z (20 bytes)\n",
        )
        create_registry.assert_called_once_with(
            ollama_base_url="http://127.0.0.1:11434",
            ollama_timeout=5.0,
            lm_studio_base_url="http://127.0.0.1:1234/v1",
            lm_studio_timeout=5.0,
            lm_studio_model_roots=None,
            docker_timeout=4.5,
            docker_classify_ai=True,
        )


if __name__ == "__main__":
    unittest.main()
