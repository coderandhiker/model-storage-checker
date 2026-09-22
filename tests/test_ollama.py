import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from model_storage_checker.cli import EXIT_ERROR, EXIT_UNAVAILABLE, main
from model_storage_checker.errors import (
    ProviderFailureError,
    ProviderUnavailableError,
)
from model_storage_checker.models import Operation, ProviderStatus
from model_storage_checker.ollama import OllamaConfig, OllamaProvider
from model_storage_checker.providers import ProviderRegistry


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class OllamaProviderTests(unittest.TestCase):
    @patch("model_storage_checker.ollama.urlopen")
    def test_successful_response_maps_and_orders_models(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse(
            {
                "models": [
                    {
                        "name": "z-model:latest",
                        "size": 20,
                        "digest": "sha256:z",
                        "modified_at": "2026-09-22T00:00:00Z",
                        "details": {
                            "format": "gguf",
                            "family": "llama",
                            "parameter_size": "7B",
                            "quantization_level": "Q4_K_M",
                        },
                    },
                    {"name": "a-model:latest", "size": 10},
                ]
            }
        )

        result = OllamaProvider().run(Operation.LIST)

        self.assertEqual(result.status, ProviderStatus.OK)
        self.assertEqual(
            [record.model_id for record in result.records],
            ["a-model:latest", "z-model:latest"],
        )
        record = result.records[1]
        self.assertEqual(record.size_bytes, 20)
        self.assertEqual(
            dict(record.attributes),
            {
                "digest": "sha256:z",
                "family": "llama",
                "format": "gguf",
                "modified_at": "2026-09-22T00:00:00Z",
                "parameter_size": "7B",
                "quantization_level": "Q4_K_M",
            },
        )

    @patch("model_storage_checker.ollama.urlopen")
    def test_configuration_controls_url_and_timeout(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse({"models": []})
        provider = OllamaProvider(
            OllamaConfig(base_url="http://localhost:9999/", timeout=1.25)
        )

        provider.run(Operation.LIST)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:9999/api/tags")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 1.25)

    @patch(
        "model_storage_checker.ollama.urlopen",
        side_effect=URLError("connection refused"),
    )
    def test_unavailable_service_is_distinct(self, urlopen: Mock) -> None:
        with self.assertRaisesRegex(
            ProviderUnavailableError, "connection refused"
        ):
            OllamaProvider().run(Operation.LIST)

    @patch("model_storage_checker.ollama.urlopen")
    def test_malformed_response_is_distinct(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse(
            {"models": [{"name": "broken", "size": "large"}]}
        )

        with self.assertRaisesRegex(
            ProviderFailureError, "malformed response.*size"
        ):
            OllamaProvider().run(Operation.LIST)

    @patch("model_storage_checker.ollama.urlopen")
    def test_empty_inventory_is_successful(self, urlopen: Mock) -> None:
        urlopen.return_value = FakeResponse({"models": []})

        result = OllamaProvider().run(Operation.LIST)

        self.assertEqual(result.status, ProviderStatus.OK)
        self.assertEqual(result.records, ())


class OllamaCliTests(unittest.TestCase):
    def test_empty_inventory_has_clear_text_output(self) -> None:
        provider = OllamaProvider()
        registry = ProviderRegistry((provider,))
        stream = io.StringIO()

        with patch(
            "model_storage_checker.ollama.urlopen",
            return_value=FakeResponse({"models": []}),
        ):
            exit_code = main(["list"], registry=registry, stdout=stream)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stream.getvalue(), "ollama: ok (0 models)\n")

    def test_failure_statuses_are_clear_in_json(self) -> None:
        provider = OllamaProvider()
        registry = ProviderRegistry((provider,))

        cases = (
            (URLError("offline"), EXIT_UNAVAILABLE, "unavailable"),
            (
                None,
                EXIT_ERROR,
                "error",
            ),
        )
        for error, expected_exit, expected_status in cases:
            with self.subTest(status=expected_status):
                stream = io.StringIO()
                effect = error
                response = (
                    None
                    if error is not None
                    else FakeResponse({"models": "not-an-array"})
                )
                with patch(
                    "model_storage_checker.ollama.urlopen",
                    side_effect=effect,
                    return_value=response,
                ):
                    exit_code = main(
                        ["list", "--output", "json"],
                        registry=registry,
                        stdout=stream,
                    )

                payload = json.loads(stream.getvalue())
                self.assertEqual(exit_code, expected_exit)
                self.assertEqual(
                    payload["providers"][0]["status"], expected_status
                )


if __name__ == "__main__":
    unittest.main()
