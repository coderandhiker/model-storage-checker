from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from model_storage_checker import ErrorCode, OllamaProvider


def response(payload: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class OllamaProviderTests(unittest.TestCase):
    def test_maps_api_fields_to_model_record(self) -> None:
        payload = {
            "models": [
                {
                    "name": "gemma3:4b",
                    "model": "gemma3:4b",
                    "modified_at": "2026-09-22T12:34:56Z",
                    "size": 3_333,
                    "digest": "sha256:abc123",
                    "details": {
                        "format": "gguf",
                        "family": "gemma3",
                        "parameter_size": "4.3B",
                        "quantization_level": "Q4_K_M",
                    },
                }
            ]
        }
        provider = OllamaProvider(
            base_url="http://ollama.example:1234/", timeout=1.5
        )

        with patch(
            "model_storage_checker.ollama.urlopen",
            return_value=response(payload),
        ) as open_url:
            status = provider.status()
            result = provider.list_models()

        self.assertTrue(status.available)
        self.assertTrue(result.succeeded)
        self.assertIsNotNone(result.value)
        self.assertEqual(open_url.call_count, 1)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "http://ollama.example:1234/api/tags")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 1.5)
        assert result.value is not None
        self.assertEqual(
            result.value[0].to_dict(),
            {
                "provider": "ollama",
                "identifier": "sha256:abc123",
                "name": "gemma3:4b",
                "size_bytes": 3_333,
                "path": None,
                "metadata": {
                    "modified_at": "2026-09-22T12:34:56Z",
                    "details": {
                        "format": "gguf",
                        "family": "gemma3",
                        "parameter_size": "4.3B",
                        "quantization_level": "Q4_K_M",
                    },
                },
            },
        )

    def test_unavailable_service_is_structured_error(self) -> None:
        provider = OllamaProvider()

        with patch(
            "model_storage_checker.ollama.urlopen",
            side_effect=URLError("connection refused"),
        ):
            status = provider.status()

        self.assertFalse(status.available)
        self.assertIn("connection refused", status.message or "")

    def test_name_is_used_when_model_and_digest_are_absent(self) -> None:
        provider = OllamaProvider()

        with patch(
            "model_storage_checker.ollama.urlopen",
            return_value=response({"models": [{"name": "llama3.2:latest"}]}),
        ):
            result = provider.list_models()

        self.assertTrue(result.succeeded)
        assert result.value is not None
        self.assertEqual(result.value[0].name, "llama3.2:latest")
        self.assertEqual(result.value[0].identifier, "llama3.2:latest")

    def test_malformed_response_is_provider_error(self) -> None:
        provider = OllamaProvider()

        with patch(
            "model_storage_checker.ollama.urlopen",
            return_value=response({"models": "not-a-list"}),
        ):
            status = provider.status()
            result = provider.list_models()

        self.assertTrue(status.available)
        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(
            result.errors[0].message,
            "Ollama API returned a malformed model inventory.",
        )

    def test_malformed_json_is_provider_error(self) -> None:
        provider = OllamaProvider()

        with patch(
            "model_storage_checker.ollama.urlopen",
            return_value=io.BytesIO(b"{not-json"),
        ):
            result = provider.list_models()

        self.assertFalse(result.succeeded)
        self.assertEqual(result.errors[0].code, ErrorCode.PROVIDER_ERROR)
        self.assertEqual(
            result.errors[0].message,
            "Ollama API returned malformed JSON.",
        )

    def test_empty_inventory_is_success(self) -> None:
        provider = OllamaProvider()

        with patch(
            "model_storage_checker.ollama.urlopen",
            return_value=response({"models": []}),
        ):
            result = provider.list_models()

        self.assertTrue(result.succeeded)
        self.assertEqual(result.value, ())


if __name__ == "__main__":
    unittest.main()
