from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from model_storage_checker import ErrorCode, LMStudioProvider


def response(payload: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class LMStudioProviderTests(unittest.TestCase):
    def test_maps_openai_compatible_api_fields(self) -> None:
        with tempfile.TemporaryDirectory() as model_root:
            provider = LMStudioProvider(
                base_url="http://lm-studio.example:1234/",
                timeout=1.5,
                model_roots=(model_root,),
            )
            payload = {
                "object": "list",
                "data": [
                    {
                        "id": "publisher/model",
                        "object": "model",
                        "created": 1_234,
                        "owned_by": "organization_owner",
                    }
                ],
            }

            with patch(
                "model_storage_checker.lm_studio.urlopen",
                return_value=response(payload),
            ) as open_url:
                status = provider.status()
                result = provider.list_models()

        self.assertTrue(status.available)
        self.assertTrue(result.succeeded)
        self.assertEqual(open_url.call_count, 1)
        request = open_url.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://lm-studio.example:1234/v1/models",
        )
        self.assertEqual(open_url.call_args.kwargs["timeout"], 1.5)
        assert result.value is not None
        self.assertEqual(
            result.value[0].to_dict(),
            {
                "provider": "lm-studio",
                "identifier": "publisher/model",
                "name": "publisher/model",
                "size_bytes": None,
                "path": None,
                "metadata": {
                    "source": "api",
                    "endpoint": (
                        "http://lm-studio.example:1234/v1/models"
                    ),
                    "object": "model",
                    "owned_by": "organization_owner",
                    "created": 1_234,
                },
            },
        )

    def test_recursively_aggregates_files_and_merges_unique_api_match(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as model_root:
            model_directory = (
                Path(model_root) / "publisher" / "example-model"
            )
            model_directory.mkdir(parents=True)
            weights = model_directory / "example-model-Q4_K_M.gguf"
            config = model_directory / "config.json"
            tokenizer_directory = model_directory / "tokenizer"
            tokenizer_directory.mkdir()
            tokenizer = tokenizer_directory / "tokenizer.json"
            weights.write_bytes(b"weights")
            config.write_bytes(b"{}")
            tokenizer.write_bytes(b"tokens")
            provider = LMStudioProvider(model_roots=(model_root,))

            with patch(
                "model_storage_checker.lm_studio.urlopen",
                return_value=response(
                    {"data": [{"id": "publisher/example-model"}]}
                ),
            ):
                result = provider.list_models()

        self.assertTrue(result.succeeded)
        assert result.value is not None
        self.assertEqual(len(result.value), 1)
        record = result.value[0]
        self.assertEqual(record.identifier, "publisher/example-model")
        self.assertEqual(record.size_bytes, 15)
        self.assertEqual(record.path, str(model_directory))
        self.assertEqual(record.metadata["source"], "api+filesystem")
        self.assertEqual(
            record.metadata["artifacts"],
            [
                {"path": str(config), "size_bytes": 2},
                {"path": str(weights), "size_bytes": 7},
                {"path": str(tokenizer), "size_bytes": 6},
            ],
        )

    def test_filesystem_inventory_survives_unavailable_api(self) -> None:
        with tempfile.TemporaryDirectory() as model_root:
            model_directory = Path(model_root) / "publisher" / "model"
            model_directory.mkdir(parents=True)
            (model_directory / "model.safetensors").write_bytes(b"1234")
            provider = LMStudioProvider(model_roots=(model_root,))

            with patch(
                "model_storage_checker.lm_studio.urlopen",
                side_effect=URLError("connection refused"),
            ):
                status = provider.status()
                result = provider.list_models()

        self.assertTrue(status.available)
        self.assertIn("filesystem inventory", status.message or "")
        self.assertTrue(result.succeeded)
        assert result.value is not None
        self.assertEqual(result.value[0].size_bytes, 4)
        self.assertIn("api_unavailable", result.value[0].metadata)
        self.assertIn(
            "connection refused",
            result.value[0].metadata["api_unavailable"]["reason"],
        )

    def test_unavailable_api_without_disk_models_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as model_root:
            provider = LMStudioProvider(model_roots=(model_root,))

            with patch(
                "model_storage_checker.lm_studio.urlopen",
                side_effect=URLError("connection refused"),
            ):
                result = provider.list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(
            result.errors[0].code,
            ErrorCode.PROVIDER_UNAVAILABLE,
        )

    def test_absent_model_directory_is_distinct_error(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            missing_root = Path(parent) / "missing"
            provider = LMStudioProvider(model_roots=(missing_root,))

            with patch(
                "model_storage_checker.lm_studio.urlopen",
                return_value=response({"data": []}),
            ):
                result = provider.list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(
            result.errors[0].details["reason"],
            "model_root_absent",
        )
        self.assertEqual(
            result.errors[0].details["model_roots"],
            [str(missing_root)],
        )

    def test_malformed_api_inventory_is_provider_error(self) -> None:
        with tempfile.TemporaryDirectory() as model_root:
            provider = LMStudioProvider(model_roots=(model_root,))

            with patch(
                "model_storage_checker.lm_studio.urlopen",
                return_value=response({"data": "not-a-list"}),
            ):
                result = provider.list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(
            result.errors[0].message,
            "LM Studio API returned a malformed model inventory.",
        )

    def test_filesystem_permission_error_is_provider_error(self) -> None:
        with tempfile.TemporaryDirectory() as model_root:
            provider = LMStudioProvider(model_roots=(model_root,))

            with (
                patch(
                    "model_storage_checker.lm_studio.urlopen",
                    return_value=response({"data": []}),
                ),
                patch.object(
                    provider,
                    "_scan_root",
                    side_effect=PermissionError(
                        13, "Permission denied", model_root
                    ),
                ),
            ):
                result = provider.list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(
            result.errors[0].details["reason"],
            "filesystem_error",
        )
        self.assertIn("Permission denied", result.errors[0].details["error"])

    def test_existing_empty_directory_and_empty_api_is_success(self) -> None:
        with tempfile.TemporaryDirectory() as model_root:
            provider = LMStudioProvider(model_roots=(model_root,))

            with patch(
                "model_storage_checker.lm_studio.urlopen",
                return_value=response({"data": []}),
            ):
                result = provider.list_models()

        self.assertTrue(result.succeeded)
        self.assertEqual(result.value, ())

    def test_ambiguous_filesystem_match_is_not_deduplicated(self) -> None:
        with (
            tempfile.TemporaryDirectory() as first_root,
            tempfile.TemporaryDirectory() as second_root,
        ):
            for root in (first_root, second_root):
                model_directory = Path(root) / "publisher" / "model"
                model_directory.mkdir(parents=True)
                (model_directory / "model.gguf").write_bytes(b"x")
            provider = LMStudioProvider(
                model_roots=(first_root, second_root)
            )

            with patch(
                "model_storage_checker.lm_studio.urlopen",
                return_value=response(
                    {"data": [{"id": "publisher/model"}]}
                ),
            ):
                result = provider.list_models()

        self.assertTrue(result.succeeded)
        assert result.value is not None
        self.assertEqual(len(result.value), 3)
        self.assertEqual(result.value[0].metadata["source"], "api")


if __name__ == "__main__":
    unittest.main()
