from __future__ import annotations

import io
import json
import unittest

from model_storage_checker import (
    CheckerError,
    ErrorCode,
    ModelProvider,
    ModelRecord,
    OperationResult,
    ProviderRegistry,
    ProviderStatus,
)
from model_storage_checker.cli import ExitCode, main
from model_storage_checker.reporting import build_report, human_size


class FakeProvider(ModelProvider):
    def __init__(
        self,
        name: str,
        result: OperationResult[tuple[ModelRecord, ...]],
    ) -> None:
        self._name = name
        self._result = result

    @property
    def name(self) -> str:
        return self._name

    def status(self) -> ProviderStatus:
        if self._result.succeeded:
            return ProviderStatus(self.name, True)
        error = self._result.errors[0]
        return ProviderStatus(
            self.name,
            error.code is not ErrorCode.PROVIDER_UNAVAILABLE,
            error.message,
        )

    def list_models(self) -> OperationResult[tuple[ModelRecord, ...]]:
        return self._result


def record(
    provider: str,
    identifier: str,
    name: str,
    size: int | None,
    *,
    path: str | None = None,
    **metadata: object,
) -> ModelRecord:
    return ModelRecord(
        provider=provider,
        identifier=identifier,
        name=name,
        size_bytes=size,
        path=path,
        metadata=metadata,
    )


class HumanSizeTests(unittest.TestCase):
    def test_formats_bytes_and_iec_units(self) -> None:
        self.assertEqual(human_size(None), "unknown")
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(1023), "1023 B")
        self.assertEqual(human_size(1024), "1.0 KiB")
        self.assertEqual(human_size(3 * 1024**3 + 512 * 1024**2), "3.5 GiB")


class ReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = (
            record("ollama", "sha:small", "small", 500),
            record("ollama", "sha:large", "large", 4096),
            record(
                "docker",
                "image:1",
                "<none>",
                2048,
                resource_type="image",
                dangling=True,
            ),
            record(
                "docker",
                "container:1",
                "old-worker",
                128,
                resource_type="container",
                running=False,
            ),
            record(
                "docker",
                "container:2",
                "active-worker",
                None,
                resource_type="container",
                running=True,
            ),
        )
        self.registry = ProviderRegistry(
            (
                FakeProvider(
                    "ollama",
                    OperationResult.success(self.records[:2]),
                ),
                FakeProvider(
                    "docker",
                    OperationResult.success(self.records[2:]),
                ),
            )
        )

    def test_aggregates_by_provider_and_resource_with_largest_items(
        self,
    ) -> None:
        payload = build_report(self.registry).to_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["summary"]["item_count"], 5)
        self.assertEqual(payload["summary"]["known_size_count"], 4)
        self.assertEqual(payload["summary"]["total_bytes"], 6772)
        groups = {
            (group["provider"], group["resource_type"]): group
            for group in payload["summary"]["groups"]
        }
        self.assertEqual(groups[("ollama", "model")]["item_count"], 2)
        self.assertEqual(groups[("ollama", "model")]["total_bytes"], 4596)
        self.assertEqual(
            groups[("ollama", "model")]["largest_items"][0]["name"],
            "large",
        )
        self.assertEqual(
            groups[("docker", "container")]["known_size_count"], 1
        )

    def test_partial_provider_failure_preserves_successful_records(
        self,
    ) -> None:
        failing = FakeProvider(
            "broken",
            OperationResult.failure(
                CheckerError(
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    "not running",
                    provider="broken",
                )
            ),
        )
        registry = ProviderRegistry(
            (
                FakeProvider(
                    "ollama",
                    OperationResult.success((self.records[0],)),
                ),
                failing,
            )
        )

        payload = build_report(registry).to_dict()

        self.assertEqual(payload["providers_succeeded"], ["ollama"])
        self.assertEqual(len(payload["records"]), 1)
        self.assertEqual(payload["errors"][0]["provider"], "broken")
        self.assertEqual(
            payload["errors"][0]["code"], "provider_unavailable"
        )

    def test_classifies_only_supported_docker_candidates(self) -> None:
        payload = build_report(self.registry).to_dict()
        candidates = {
            item["identifier"]: item["cleanup_candidate"]
            for item in payload["records"]
        }

        self.assertTrue(candidates["image:1"]["candidate"])
        self.assertFalse(candidates["image:1"]["heuristic"])
        self.assertIn("dangling", candidates["image:1"]["reasons"][0])
        self.assertTrue(candidates["container:1"]["candidate"])
        self.assertIn("stopped", candidates["container:1"]["reasons"][0])
        self.assertFalse(candidates["container:2"]["candidate"])
        self.assertTrue(
            all(
                not candidate["automatically_safe_to_delete"]
                for candidate in candidates.values()
            )
        )

    def test_duplicate_filesystem_and_api_records_are_heuristic_candidates(
        self,
    ) -> None:
        duplicates = (
            record(
                "lm-studio",
                "org/model.gguf",
                "Model GGUF",
                None,
                source="api",
            ),
            record(
                "lm-studio",
                "/models/org/model-gguf",
                "org/model-gguf",
                100,
                path="/models/org/model-gguf",
                source="filesystem",
                relative_path="org/model-gguf",
            ),
            record(
                "lm-studio",
                "other",
                "other",
                None,
                source="api",
            ),
        )
        registry = ProviderRegistry(
            (FakeProvider("lm-studio", OperationResult.success(duplicates)),)
        )

        payload = build_report(registry).to_dict()
        assessments = {
            item["identifier"]: item["cleanup_candidate"]
            for item in payload["records"]
        }

        self.assertTrue(assessments["org/model.gguf"]["candidate"])
        self.assertTrue(assessments["org/model.gguf"]["heuristic"])
        self.assertIn(
            "Heuristic:", assessments["org/model.gguf"]["reasons"][0]
        )
        self.assertTrue(
            assessments["/models/org/model-gguf"]["candidate"]
        )
        self.assertFalse(assessments["other"]["candidate"])

    def test_filters_and_largest_first_sort_are_deterministic(self) -> None:
        first = build_report(
            self.registry,
            providers=("docker",),
            resources=("container",),
            minimum_size=100,
            largest_first=True,
            candidates_only=True,
        ).to_dict()
        second = build_report(
            self.registry,
            providers=("docker",),
            resources=("container",),
            minimum_size=100,
            largest_first=True,
            candidates_only=True,
        ).to_dict()

        self.assertEqual(first, second)
        self.assertEqual(
            [item["identifier"] for item in first["records"]],
            ["container:1"],
        )
        self.assertEqual(first["filters"]["sort"], "largest_first")

    def test_default_sort_uses_provider_resource_and_name(self) -> None:
        identifiers = [
            item["identifier"]
            for item in build_report(self.registry).to_dict()["records"]
        ]

        self.assertEqual(
            identifiers,
            ["container:2", "container:1", "image:1", "sha:large", "sha:small"],
        )


class ReportCliContractTests(unittest.TestCase):
    def test_json_contract_and_partial_failure_exit_success(self) -> None:
        registry = ProviderRegistry(
            (
                FakeProvider(
                    "good",
                    OperationResult.success(
                        (record("good", "one", "one", 1024),)
                    ),
                ),
                FakeProvider(
                    "bad",
                    OperationResult.failure(
                        CheckerError(
                            ErrorCode.PROVIDER_ERROR,
                            "failed",
                            provider="bad",
                        )
                    ),
                ),
            )
        )
        stdout = io.StringIO()

        exit_code = main(
            ["--output", "json", "report"],
            stdout=stdout,
            registry=registry,
        )

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            set(payload),
            {
                "schema_version",
                "providers_requested",
                "providers_succeeded",
                "filters",
                "summary",
                "records",
                "warnings",
                "errors",
            },
        )
        self.assertEqual(payload["records"][0]["identifier"], "one")
        self.assertEqual(payload["errors"][0]["provider"], "bad")
        self.assertIn("advisory only", payload["warnings"][0])

    def test_text_contract_shows_summary_candidates_warning_and_errors(
        self,
    ) -> None:
        registry = ProviderRegistry(
            (
                FakeProvider(
                    "docker",
                    OperationResult.success(
                        (
                            record(
                                "docker",
                                "image:old",
                                "<none>",
                                2048,
                                resource_type="image",
                                dangling=True,
                            ),
                        )
                    ),
                ),
                FakeProvider(
                    "offline",
                    OperationResult.failure(
                        CheckerError(
                            ErrorCode.PROVIDER_UNAVAILABLE,
                            "offline",
                            provider="offline",
                        )
                    ),
                ),
            )
        )
        stdout = io.StringIO()

        exit_code = main(["report"], stdout=stdout, registry=registry)
        output = stdout.getvalue()

        self.assertEqual(exit_code, ExitCode.SUCCESS)
        self.assertIn("Storage summary: 1 items, 2.0 KiB", output)
        self.assertIn("docker / image: 1 items", output)
        self.assertIn("Cleanup candidates (manual review required):", output)
        self.assertIn("warning: Cleanup candidates are advisory only.", output)
        self.assertIn(
            "error: provider_unavailable [offline]: offline", output
        )


if __name__ == "__main__":
    unittest.main()
