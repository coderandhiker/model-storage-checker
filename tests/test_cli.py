from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from model_storage_checker.cli import ExitCode, main


class CliTests(unittest.TestCase):
    def test_providers_text_output_is_explicit(self) -> None:
        stdout = io.StringIO()

        exit_code = main(["providers"], stdout=stdout)

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertEqual(stdout.getvalue(), "No providers are registered.\n")

    def test_providers_json_output_has_stable_shape(self) -> None:
        stdout = io.StringIO()

        exit_code = main(
            ["--output", "json", "providers"], stdout=stdout
        )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertEqual(json.loads(stdout.getvalue()), {"providers": []})

    def test_missing_provider_is_a_json_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["--output", "json", "list", "--provider", "ollama"],
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
                        "message": "Provider 'ollama' is not registered.",
                        "provider": "ollama",
                    }
                ]
            },
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
                "--output",
                "json",
                "providers",
            ],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, ExitCode.SUCCESS)
        self.assertEqual(json.loads(completed.stdout), {"providers": []})
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
