import subprocess
import unittest
from unittest.mock import call, patch

from model_storage_checker.docker import DockerConfig, DockerProvider
from model_storage_checker.errors import (
    ProviderFailureError,
    ProviderUnavailableError,
)
from model_storage_checker.models import Operation


IMAGE_JSON = (
    '{"Containers":"1","CreatedAt":"2026-09-20 10:11:12 -0700 PDT",'
    '"CreatedSince":"2 days ago","Digest":"sha256:digest","ID":"sha256:image",'
    '"Repository":"example/ollama","SharedSize":"10MB","Size":"1.5GB",'
    '"Tag":"latest","UniqueSize":"1.49GB"}\n'
)
CONTAINER_JSON = (
    '{"Command":"\\"serve\\"","CreatedAt":"2026-09-21 10:11:12 -0700 PDT",'
    '"ID":"container-id","Image":"example/ollama:latest","Labels":"role=inference",'
    '"LocalVolumes":"1","Mounts":"models","Names":"model-server",'
    '"Networks":"bridge","Ports":"11434/tcp","RunningFor":"1 day ago",'
    '"Size":"12kB (virtual 1.5GB)","State":"exited",'
    '"Status":"Exited (0) 2 hours ago"}\n'
)


def completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=("docker",), returncode=returncode, stdout=stdout, stderr=stderr
    )


class DockerProviderTests(unittest.TestCase):
    def test_uses_only_explicit_read_only_argument_arrays(self) -> None:
        provider = DockerProvider(DockerConfig(timeout=2.5))

        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=[completed(IMAGE_JSON), completed(CONTAINER_JSON)],
        ) as run:
            provider.run(Operation.LIST)

        self.assertEqual(
            run.call_args_list,
            [
                call(
                    (
                        "docker",
                        "image",
                        "ls",
                        "--all",
                        "--no-trunc",
                        "--digests",
                        "--format",
                        "{{json .}}",
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2.5,
                ),
                call(
                    (
                        "docker",
                        "container",
                        "ls",
                        "--all",
                        "--no-trunc",
                        "--size",
                        "--format",
                        "{{json .}}",
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2.5,
                ),
            ],
        )

    def test_maps_all_image_and_container_inventory_fields(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=[completed(IMAGE_JSON), completed(CONTAINER_JSON)],
        ):
            result = DockerProvider().run(Operation.LIST)

        self.assertEqual(len(result.records), 2)
        by_kind = {
            record.attributes["inventory.kind"]: record for record in result.records
        }
        image = by_kind["image"]
        container = by_kind["container"]
        self.assertEqual(image.model_id, "image:sha256:image")
        self.assertEqual(image.location, "example/ollama:latest")
        self.assertEqual(image.size_bytes, 1_500_000_000)
        self.assertEqual(
            {
                key: image.attributes[f"docker.{key}"]
                for key in (
                    "Containers",
                    "CreatedAt",
                    "CreatedSince",
                    "Digest",
                    "ID",
                    "Repository",
                    "SharedSize",
                    "Size",
                    "Tag",
                    "UniqueSize",
                )
            },
            {
                "Containers": "1",
                "CreatedAt": "2026-09-20 10:11:12 -0700 PDT",
                "CreatedSince": "2 days ago",
                "Digest": "sha256:digest",
                "ID": "sha256:image",
                "Repository": "example/ollama",
                "SharedSize": "10MB",
                "Size": "1.5GB",
                "Tag": "latest",
                "UniqueSize": "1.49GB",
            },
        )

        self.assertEqual(container.model_id, "container:container-id")
        self.assertEqual(container.location, "model-server")
        self.assertEqual(container.size_bytes, 12_000)
        self.assertEqual(container.attributes["docker.State"], "exited")
        self.assertEqual(
            container.attributes["docker.Status"], "Exited (0) 2 hours ago"
        )
        self.assertEqual(container.attributes["docker.Command"], '"serve"')
        self.assertEqual(container.attributes["docker.Labels"], "role=inference")
        self.assertEqual(container.attributes["docker.LocalVolumes"], "1")
        self.assertEqual(container.attributes["docker.Mounts"], "models")
        self.assertEqual(container.attributes["docker.Networks"], "bridge")
        self.assertEqual(container.attributes["docker.Ports"], "11434/tcp")
        self.assertEqual(container.attributes["docker.RunningFor"], "1 day ago")
        self.assertEqual(
            container.attributes["image.relationship"],
            "example/ollama:latest",
        )

    def test_missing_cli_is_distinct(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            with self.assertRaisesRegex(
                ProviderUnavailableError, "Docker CLI is missing"
            ):
                DockerProvider().run(Operation.LIST)

    def test_unavailable_daemon_is_distinct(self) -> None:
        failure = completed(
            stderr="Cannot connect to the Docker daemon at unix:///socket.",
            returncode=1,
        )
        with patch(
            "model_storage_checker.docker.subprocess.run", return_value=failure
        ):
            with self.assertRaisesRegex(
                ProviderUnavailableError, "Docker daemon is unavailable"
            ):
                DockerProvider().run(Operation.LIST)

    def test_permission_denied_is_distinct(self) -> None:
        failure = completed(
            stderr="permission denied connecting to socket", returncode=1
        )
        with patch(
            "model_storage_checker.docker.subprocess.run", return_value=failure
        ):
            with self.assertRaisesRegex(
                ProviderUnavailableError, "permission denied while accessing Docker"
            ):
                DockerProvider().run(Operation.LIST)

    def test_timeout_is_distinct(self) -> None:
        timeout = subprocess.TimeoutExpired(("docker",), 3)
        with patch(
            "model_storage_checker.docker.subprocess.run", side_effect=timeout
        ):
            with self.assertRaisesRegex(
                ProviderUnavailableError,
                "image inventory timed out after 3 seconds",
            ):
                DockerProvider(DockerConfig(timeout=3)).run(Operation.LIST)

    def test_other_cli_failure_is_an_error(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            return_value=completed(returncode=125),
        ):
            with self.assertRaisesRegex(
                ProviderFailureError,
                "image inventory command exited with status 125",
            ):
                DockerProvider().run(Operation.LIST)

    def test_malformed_output_is_an_error(self) -> None:
        malformed_outputs = (
            "not-json\n",
            "[]\n",
            '{"ID":"only-an-id"}\n',
            '{"ID":3}\n',
            IMAGE_JSON.replace('"Size":"1.5GB"', '"Size":"unknown"'),
            "\n",
        )
        for output in malformed_outputs:
            with self.subTest(output=output):
                with patch(
                    "model_storage_checker.docker.subprocess.run",
                    side_effect=[completed(output), completed()],
                ):
                    with self.assertRaisesRegex(
                        ProviderFailureError, "malformed Docker image output"
                    ):
                        DockerProvider().run(Operation.LIST)

    def test_empty_output_is_a_successful_empty_inventory(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=[completed(), completed()],
        ):
            result = DockerProvider().run(Operation.LIST)

        self.assertEqual(result.records, ())
        self.assertEqual(result.status.value, "ok")

    def test_optional_heuristic_labels_without_filtering(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=[completed(IMAGE_JSON), completed(CONTAINER_JSON)],
        ):
            result = DockerProvider(
                DockerConfig(classify_ai=True)
            ).run(Operation.LIST)

        self.assertEqual(len(result.records), 2)
        for record in result.records:
            self.assertEqual(record.attributes["heuristic.classification"], "optional")
            self.assertEqual(record.attributes["heuristic.ai_related"], "true")
            self.assertEqual(record.attributes["heuristic.match"], "ollama")

    def test_heuristic_is_absent_by_default(self) -> None:
        with patch(
            "model_storage_checker.docker.subprocess.run",
            side_effect=[completed(IMAGE_JSON), completed()],
        ):
            result = DockerProvider().run(Operation.LIST)

        self.assertNotIn("heuristic.classification", result.records[0].attributes)


if __name__ == "__main__":
    unittest.main()
