import unittest

from model_storage_checker.models import (
    ModelRecord,
    Operation,
    ProviderResult,
    ProviderStatus,
)
from model_storage_checker.reporting import (
    build_summary,
    find_cleanup_candidates,
)


class ReportingTests(unittest.TestCase):
    def test_summary_groups_provider_and_resource_type(self) -> None:
        results = (
            ProviderResult.success(
                "ollama",
                Operation.LIST,
                (ModelRecord("ollama", "one", 100),),
            ),
            ProviderResult.success(
                "docker",
                Operation.LIST,
                (
                    ModelRecord(
                        "docker",
                        "image:one",
                        200,
                        attributes={"inventory.kind": "image"},
                    ),
                    ModelRecord(
                        "docker",
                        "container:one",
                        30,
                        attributes={"inventory.kind": "container"},
                    ),
                ),
            ),
        )

        summary = build_summary(results).to_dict()

        self.assertEqual(summary["total"]["total_size_bytes"], 330)
        self.assertEqual(
            summary["by_provider"]["docker"]["record_count"], 2
        )
        self.assertEqual(
            summary["by_resource_type"]["image"]["known_size_bytes"], 200
        )
        self.assertEqual(
            summary["by_provider_and_resource_type"]["docker"]["container"][
                "record_count"
            ],
            1,
        )

    def test_unknown_size_makes_complete_total_unknown(self) -> None:
        result = ProviderResult.success(
            "lm-studio",
            Operation.LIST,
            (
                ModelRecord("lm-studio", "known", 50),
                ModelRecord("lm-studio", "unknown"),
            ),
        )

        total = build_summary((result,)).total

        self.assertEqual(total.known_size_bytes, 50)
        self.assertEqual(total.unknown_size_count, 1)
        self.assertIsNone(total.total_size_bytes)

    def test_failed_provider_and_partial_records_are_aggregated(self) -> None:
        result = ProviderResult.failure(
            "lm-studio",
            Operation.LIST,
            ProviderStatus.ERROR,
            "API discovery failed",
            (ModelRecord("lm-studio", "local", 75),),
        )

        summary = build_summary((result,))

        self.assertEqual(summary.total.record_count, 1)
        self.assertEqual(summary.total.total_size_bytes, 75)
        self.assertEqual(summary.by_provider["lm-studio"].record_count, 1)

    def test_candidates_are_conservative_advisory_heuristics(self) -> None:
        result = ProviderResult.success(
            "docker",
            Operation.LIST,
            (
                self._docker_record(
                    "image:dangling",
                    "image",
                    **{"docker.Repository": "<none>", "docker.Tag": "<none>"},
                ),
                self._docker_record(
                    "container:old", "container", **{"docker.State": "exited"}
                ),
                self._docker_record(
                    "container:running",
                    "container",
                    **{"docker.State": "running"},
                ),
                self._docker_record(
                    "image:tagged",
                    "image",
                    **{"docker.Repository": "example", "docker.Tag": "latest"},
                ),
                self._docker_record("image:incomplete", "image"),
            ),
        )

        candidates = find_cleanup_candidates((result,))
        payloads = [candidate.to_dict() for candidate in candidates]

        self.assertEqual(
            [candidate.record_id for candidate in candidates],
            ["container:old", "image:dangling"],
        )
        self.assertTrue(all(item["advisory_only"] for item in payloads))
        self.assertTrue(
            all(item["classification"] == "heuristic" for item in payloads)
        )
        self.assertTrue(
            all(item["evidence_kind"] == "reported_metadata" for item in payloads)
        )
        self.assertIn("does not prove", payloads[0]["rationale"])

    @staticmethod
    def _docker_record(
        record_id: str, kind: str, **attributes: str
    ) -> ModelRecord:
        return ModelRecord(
            "docker",
            record_id,
            attributes={"inventory.kind": kind, **attributes},
        )


if __name__ == "__main__":
    unittest.main()
