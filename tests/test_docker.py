from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import call, patch

from model_storage_checker import DockerProvider, ErrorCode


def completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def lines(*payloads: object) -> str:
    return "".join(f"{json.dumps(payload)}\n" for payload in payloads)


class DockerProviderTests(unittest.TestCase):
    def test_constructs_read_only_machine_readable_commands(self) -> None:
        provider = DockerProvider(executable="/opt/bin/docker", timeout=1.25)

        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=(completed(), completed()),
        ) as run:
            status = provider.status()
            result = provider.list_models()

        self.assertTrue(status.available)
        self.assertTrue(result.succeeded)
        self.assertEqual(result.value, ())
        self.assertEqual(run.call_count, 2)
        common = {
            "check": False,
            "capture_output": True,
            "text": True,
            "timeout": 1.25,
        }
        self.assertEqual(
            run.call_args_list,
            [
                call(
                    [
                        "/opt/bin/docker",
                        "image",
                        "ls",
                        "--all",
                        "--no-trunc",
                        "--digests",
                        "--format",
                        "{{json .}}",
                    ],
                    **common,
                ),
                call(
                    [
                        "/opt/bin/docker",
                        "container",
                        "ls",
                        "--all",
                        "--no-trunc",
                        "--size",
                        "--format",
                        "{{json .}}",
                    ],
                    **common,
                ),
            ],
        )

    def test_parses_all_images_and_containers_with_cleanup_metadata(
        self,
    ) -> None:
        image_output = lines(
            {
                "ID": "sha256:111",
                "Repository": "ollama/ollama",
                "Tag": "latest",
                "Digest": "sha256:aaa",
                "CreatedAt": "2026-09-20 10:00:00 -0700 PDT",
                "Size": "4.4GB",
                "VirtualSize": "4.5GB",
                "SharedSize": "1.25GB",
                "UniqueSize": "3.25GB",
                "Containers": "2",
                "Labels": "org.opencontainers.image.title=Ollama",
            },
            {
                "ID": "sha256:222",
                "Repository": "ordinary/app",
                "Tag": "v1",
                "CreatedAt": "2026-09-19 10:00:00 -0700 PDT",
                "Size": "125MB",
                "SharedSize": "N/A",
            },
            {
                "ID": "sha256:333",
                "Repository": "<none>",
                "Tag": "<none>",
                "CreatedAt": "2026-09-18 10:00:00 -0700 PDT",
                "Size": "12kB",
                "SharedSize": "0B",
            },
        )
        container_output = lines(
            {
                "ID": "a" * 64,
                "Names": "localai",
                "Image": "localai/localai:latest",
                "ImageID": "sha256:444",
                "State": "running",
                "Status": "Up 2 hours",
                "CreatedAt": "2026-09-22 08:00:00 -0700 PDT",
                "Size": "35.58kB (virtual 109.2MB)",
                "Labels": "purpose=inference",
                "Mounts": "/models",
                "Networks": "bridge",
                "Ports": "8080/tcp",
            },
            {
                "ID": "b" * 64,
                "Names": "database",
                "Image": "postgres:17",
                "State": "exited",
                "Status": "Exited (0) 1 day ago",
                "CreatedAt": "2026-09-20 08:00:00 -0700 PDT",
                "Size": "0B (virtual 450MB)",
            },
        )
        provider = DockerProvider()

        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=(
                completed(stdout=image_output),
                completed(stdout=container_output),
            ),
        ):
            result = provider.list_models()

        self.assertTrue(result.succeeded)
        assert result.value is not None
        self.assertEqual(len(result.value), 5)
        first_image = result.value[0]
        self.assertEqual(first_image.name, "ollama/ollama:latest")
        self.assertEqual(first_image.size_bytes, 4_500_000_000)
        self.assertEqual(
            first_image.metadata["shared_size_bytes"], 1_250_000_000
        )
        self.assertEqual(first_image.metadata["digest"], "sha256:aaa")
        self.assertEqual(first_image.metadata["container_count"], "2")
        self.assertTrue(
            first_image.metadata["local_ai_classification"]["likely_local_ai"]
        )
        ordinary_image = result.value[1]
        self.assertFalse(
            ordinary_image.metadata["local_ai_classification"][
                "likely_local_ai"
            ]
        )
        dangling_image = result.value[2]
        self.assertTrue(dangling_image.metadata["dangling"])
        self.assertEqual(dangling_image.name, "sha256:333")

        running = result.value[3]
        self.assertEqual(running.metadata["resource_type"], "container")
        self.assertTrue(running.metadata["running"])
        self.assertEqual(running.size_bytes, 35_580)
        self.assertEqual(running.metadata["virtual_size_bytes"], 109_200_000)
        self.assertEqual(running.metadata["image_id"], "sha256:444")
        stopped = result.value[4]
        self.assertFalse(stopped.metadata["running"])
        self.assertEqual(stopped.metadata["state"], "exited")
        self.assertEqual(stopped.metadata["status"], "Exited (0) 1 day ago")

    def test_missing_cli_is_distinct_unavailable_error(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = DockerProvider().list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_UNAVAILABLE)
        self.assertEqual(result.errors[0].details["reason"], "cli_missing")

    def test_daemon_unavailable_is_distinct_unavailable_error(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            return_value=completed(
                stderr=(
                    "Cannot connect to the Docker daemon at "
                    "unix:///var/run/docker.sock. Is the docker daemon running?"
                ),
                returncode=1,
            ),
        ):
            result = DockerProvider().list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_UNAVAILABLE)
        self.assertEqual(
            result.errors[0].details["reason"], "daemon_unavailable"
        )

    def test_permission_denied_is_distinct_unavailable_error(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            return_value=completed(
                stderr="permission denied while trying to connect",
                returncode=1,
            ),
        ):
            result = DockerProvider().list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_UNAVAILABLE)
        self.assertEqual(
            result.errors[0].details["reason"], "permission_denied"
        )

    def test_timeout_is_provider_error(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["docker"], 5),
        ):
            result = DockerProvider().list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(result.errors[0].details["reason"], "command_timeout")

    def test_nonzero_command_failure_is_provider_error(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            return_value=completed(stderr="unexpected failure", returncode=42),
        ):
            result = DockerProvider().list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(result.errors[0].details["reason"], "command_failure")
        self.assertEqual(result.errors[0].details["exit_code"], 42)

    def test_malformed_json_is_provider_error(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=(completed(stdout="{not json}\n"), completed()),
        ):
            result = DockerProvider().list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(result.errors[0].details["reason"], "malformed_output")

    def test_undecodable_output_is_provider_error(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=UnicodeDecodeError(
                "utf-8", b"\xff", 0, 1, "invalid start byte"
            ),
        ):
            result = DockerProvider().list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(result.errors[0].details["reason"], "malformed_output")

    def test_missing_required_output_field_is_malformed(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=(
                completed(
                    stdout=lines(
                        {
                            "ID": "sha256:111",
                            "Repository": "repo",
                            "Size": "1MB",
                        }
                    )
                ),
                completed(),
            ),
        ):
            result = DockerProvider().list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].details["reason"], "malformed_output")


if __name__ == "__main__":
    unittest.main()
