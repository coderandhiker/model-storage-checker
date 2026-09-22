from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from model_storage_checker.cli import ExitCode, main
from model_storage_checker.providers import ProviderStatus
from model_storage_checker.results import OperationResult


class CliTests(unittest.TestCase):
    def test_providers_text_output_is_explicit(self) -> None:
        stdout = io.StringIO()

        with patch(
            "model_storage_checker.ollama.urlopen",
            side_effect=URLError("connection refused"),
        ), patch(
            "model_storage_checker.cli.LMStudioProvider.status",
            return_value=ProviderStatus(
                name="lm-studio",
                available=False,
                message="not running",
            ),
        ), patch(
            "model_storage_checker.cli.DockerProvider.status",
            return_value=ProviderStatus(
                name="docker",
                available=False,
                message="not running",
            ),
        ):
            exit_code = main(["providers"], stdout=stdout)

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertIn("ollama: unavailable:", stdout.getvalue())
        self.assertIn("connection refused", stdout.getvalue())

    def test_providers_json_output_has_stable_shape(self) -> None:
        stdout = io.StringIO()

        with patch(
            "model_storage_checker.ollama.urlopen",
            side_effect=URLError("connection refused"),
        ), patch(
            "model_storage_checker.cli.LMStudioProvider.status",
            return_value=ProviderStatus(
                name="lm-studio",
                available=False,
                message="not running",
            ),
        ), patch(
            "model_storage_checker.cli.DockerProvider.status",
            return_value=ProviderStatus(
                name="docker",
                available=False,
                message="not running",
            ),
        ):
            exit_code = main(
                ["--output", "json", "providers"], stdout=stdout
            )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        payload = json.loads(stdout.getvalue())
        providers = {
            provider["name"]: provider
            for provider in payload["providers"]
        }
        self.assertFalse(providers["ollama"]["available"])
        self.assertIn(
            "connection refused", providers["ollama"]["message"]
        )
        self.assertFalse(providers["lm-studio"]["available"])
        self.assertFalse(providers["docker"]["available"])

    def test_missing_provider_is_a_json_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["--output", "json", "list", "--provider", "missing"],
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, ExitCode.UNAVAILABLE)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            json.loads(stderr.getvalue()),
            {
                "errors": [
                    {
                        "code": "provider_unavailable",
                        "message": "Provider 'missing' is not registered.",
                        "provider": "missing",
                    }
                ]
            },
        )

    def test_empty_ollama_inventory_is_successful_json(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "model_storage_checker.ollama.urlopen",
            return_value=io.BytesIO(b'{"models": []}'),
        ):
            exit_code = main(
                [
                    "--output",
                    "json",
                    "--ollama-base-url",
                    "http://ollama.test:11434",
                    "list",
                    "--provider",
                    "ollama",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertEqual(json.loads(stdout.getvalue()), {"models": []})
        self.assertEqual(stderr.getvalue(), "")

    def test_unavailable_ollama_uses_unavailable_exit_code(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "model_storage_checker.ollama.urlopen",
            side_effect=URLError("connection refused"),
        ):
            exit_code = main(
                ["--output", "json", "list", "--provider", "ollama"],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, ExitCode.UNAVAILABLE)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            json.loads(stderr.getvalue())["errors"][0]["code"],
            "provider_unavailable",
        )

    def test_malformed_ollama_inventory_is_failure(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "model_storage_checker.ollama.urlopen",
            return_value=io.BytesIO(b'{"models": null}'),
        ):
            exit_code = main(
                ["--output", "json", "list", "--provider", "ollama"],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, ExitCode.FAILURE)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            json.loads(stderr.getvalue())["errors"][0]["code"],
            "provider_error",
        )

    def test_lm_studio_options_are_wired_to_provider(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as model_root:
            with patch(
                "model_storage_checker.lm_studio.urlopen",
                return_value=io.BytesIO(b'{"data": []}'),
            ) as open_url:
                exit_code = main(
                    [
                        "--output",
                        "json",
                        "--lm-studio-base-url",
                        "http://lm-studio.test:4321",
                        "--lm-studio-timeout",
                        "1.25",
                        "--lm-studio-model-root",
                        model_root,
                        "list",
                        "--provider",
                        "lm-studio",
                    ],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertEqual(json.loads(stdout.getvalue()), {"models": []})
        self.assertEqual(stderr.getvalue(), "")
        request = open_url.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://lm-studio.test:4321/v1/models",
        )
        self.assertEqual(open_url.call_args.kwargs["timeout"], 1.25)

    def test_docker_options_are_wired_to_provider(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "model_storage_checker.cli.DockerProvider"
        ) as provider_type:
            provider = provider_type.return_value
            provider.name = "docker"
            provider.status.return_value = ProviderStatus(
                name="docker", available=True
            )
            provider.list_models.return_value = OperationResult.success(())
            exit_code = main(
                [
                    "--output",
                    "json",
                    "--docker-executable",
                    "/opt/bin/docker",
                    "--docker-timeout",
                    "1.75",
                    "list",
                    "--provider",
                    "docker",
                ],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertEqual(json.loads(stdout.getvalue()), {"models": []})
        self.assertEqual(stderr.getvalue(), "")
        provider_type.assert_called_once_with(
            executable="/opt/bin/docker",
            timeout=1.75,
        )

    def test_module_entry_point_runs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "model_storage_checker",
                "--help",
            ],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, ExitCode.SUCCESS)
        self.assertIn("--ollama-base-url", completed.stdout)
        self.assertIn("--lm-studio-base-url", completed.stdout)
        self.assertIn("--lm-studio-model-root", completed.stdout)
        self.assertIn("--docker-executable", completed.stdout)
        self.assertIn("--docker-timeout", completed.stdout)
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
