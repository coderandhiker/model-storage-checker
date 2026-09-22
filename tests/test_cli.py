from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError

from model_storage_checker.cli import ExitCode, main


class CliTests(unittest.TestCase):
    def test_providers_text_output_is_explicit(self) -> None:
        stdout = io.StringIO()

        with patch(
            "model_storage_checker.ollama.urlopen",
            side_effect=URLError("connection refused"),
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
        ):
            exit_code = main(
                ["--output", "json", "providers"], stdout=stdout
            )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["providers"][0]["name"], "ollama")
        self.assertFalse(payload["providers"][0]["available"])
        self.assertIn(
            "connection refused", payload["providers"][0]["message"]
        )

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
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
