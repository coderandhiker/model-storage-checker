import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError

from model_storage_checker.lm_studio import LMStudioConfig, LMStudioProvider
from model_storage_checker.models import Operation, ProviderStatus


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class LMStudioProviderTests(unittest.TestCase):
    @patch("model_storage_checker.lm_studio.urlopen")
    def test_api_metadata_url_and_timeout(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse(
            {
                "data": [
                    {
                        "id": "publisher/model",
                        "object": "model",
                        "owned_by": "publisher",
                        "created": 123,
                    }
                ]
            }
        )
        provider = LMStudioProvider(
            LMStudioConfig(
                base_url="http://localhost:9999/v1/",
                timeout=1.25,
                model_roots=(),
            )
        )

        result = provider.run(Operation.LIST)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:9999/v1/models")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 1.25)
        self.assertEqual(
            dict(result.records[0].attributes),
            {
                "api.created": "123",
                "api.object": "model",
                "api.owned_by": "publisher",
                "source": "api",
            },
        )

    @patch("model_storage_checker.lm_studio.urlopen")
    def test_recursively_discovers_model_files_with_sizes(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse({"data": []})
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            model = root / "publisher" / "nested" / "model.gguf"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"model-data")
            (model.parent / "metadata.json").write_text("{}")
            resolved_root = root.resolve()
            resolved_model = resolved_root / "publisher" / "nested" / "model.gguf"

            result = LMStudioProvider(
                LMStudioConfig(model_roots=(root,))
            ).run(Operation.LIST)

        self.assertEqual(result.status, ProviderStatus.OK)
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.model_id, "publisher/nested/model")
        self.assertEqual(record.size_bytes, 10)
        self.assertEqual(record.location, str(resolved_model))
        self.assertEqual(
            dict(record.attributes),
            {
                "filesystem.extension": ".gguf",
                "filesystem.relative_path": "publisher/nested/model.gguf",
                "filesystem.root": str(resolved_root),
                "source": "filesystem",
            },
        )

    @patch("model_storage_checker.lm_studio.urlopen")
    def test_combined_sources_deduplicate_by_exact_id(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse(
            {
                "data": [
                    {
                        "id": "publisher/model",
                        "object": "model",
                        "owned_by": "publisher",
                    },
                    {"id": "api-only"},
                ]
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            matching = root / "publisher" / "model.gguf"
            similarly_named = root / "other" / "model.gguf"
            matching.parent.mkdir()
            similarly_named.parent.mkdir()
            matching.write_bytes(b"123")
            similarly_named.write_bytes(b"12345")

            first = LMStudioProvider(
                LMStudioConfig(model_roots=(root,))
            ).run(Operation.LIST)
            second = LMStudioProvider(
                LMStudioConfig(model_roots=(root,))
            ).run(Operation.LIST)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            [record.model_id for record in first.records],
            ["api-only", "other/model", "publisher/model"],
        )
        merged = first.records[2]
        self.assertEqual(merged.size_bytes, 3)
        self.assertEqual(merged.attributes["source"], "api,filesystem")
        self.assertEqual(merged.attributes["api.owned_by"], "publisher")
        self.assertNotIn("api.owned_by", first.records[1].attributes)

    @patch(
        "model_storage_checker.lm_studio.urlopen",
        side_effect=URLError("connection refused"),
    )
    def test_api_error_preserves_filesystem_records(self, urlopen: Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            model = root / "local.gguf"
            model.write_bytes(b"local")

            result = LMStudioProvider(
                LMStudioConfig(model_roots=(root,))
            ).run(Operation.LIST)

        self.assertEqual(result.status, ProviderStatus.UNAVAILABLE)
        self.assertEqual([record.model_id for record in result.records], ["local"])
        self.assertIn("API discovery failed", result.message or "")
        self.assertNotIn("filesystem discovery failed", result.message or "")

    @patch("model_storage_checker.lm_studio.urlopen")
    def test_filesystem_error_preserves_api_records(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse({"data": [{"id": "api-model"}]})
        with tempfile.TemporaryDirectory() as temporary_directory:
            invalid_root = Path(temporary_directory) / "missing"

            result = LMStudioProvider(
                LMStudioConfig(model_roots=(invalid_root,))
            ).run(Operation.LIST)

        self.assertEqual(result.status, ProviderStatus.ERROR)
        self.assertEqual([record.model_id for record in result.records], ["api-model"])
        self.assertIn("filesystem discovery failed", result.message or "")
        self.assertIn("root does not exist", result.message or "")

    @patch("model_storage_checker.lm_studio.urlopen")
    def test_malformed_api_preserves_filesystem_records(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse({"data": [{"id": 123}]})
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "local.safetensors").write_bytes(b"x")

            result = LMStudioProvider(
                LMStudioConfig(model_roots=(root,))
            ).run(Operation.LIST)

        self.assertEqual(result.status, ProviderStatus.ERROR)
        self.assertEqual([record.model_id for record in result.records], ["local"])
        self.assertIn("malformed response", result.message or "")

    @patch("model_storage_checker.lm_studio.urlopen")
    def test_duplicate_api_observations_merge_stably(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse(
            {
                "data": [
                    {"id": "duplicate", "owned_by": "z-owner"},
                    {"id": "duplicate", "owned_by": "a-owner"},
                ]
            }
        )

        result = LMStudioProvider(
            LMStudioConfig(model_roots=())
        ).run(Operation.LIST)

        self.assertEqual(len(result.records), 1)
        self.assertEqual(
            result.records[0].attributes["api.owned_by"],
            '["a-owner","z-owner"]',
        )

    @patch("model_storage_checker.lm_studio.urlopen")
    def test_empty_sources_are_successful(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse({"data": []})
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = LMStudioProvider(
                LMStudioConfig(model_roots=(Path(temporary_directory),))
            ).run(Operation.LIST)

        self.assertEqual(result.status, ProviderStatus.OK)
        self.assertEqual(result.records, ())


if __name__ == "__main__":
    unittest.main()
