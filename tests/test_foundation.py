from __future__ import annotations

import unittest

from model_storage_checker import (
    CheckerError,
    ErrorCode,
    ModelRecord,
    OperationResult,
    ProviderRegistry,
)


class ModelRecordTests(unittest.TestCase):
    def test_record_serializes_all_fields(self) -> None:
        record = ModelRecord(
            provider="example",
            identifier="model:latest",
            name="Example Model",
            size_bytes=42,
            path="/models/example",
            metadata={"format": "test"},
        )

        self.assertEqual(
            record.to_dict(),
            {
                "provider": "example",
                "identifier": "model:latest",
                "name": "Example Model",
                "size_bytes": 42,
                "path": "/models/example",
                "metadata": {"format": "test"},
            },
        )

    def test_record_rejects_invalid_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider"):
            ModelRecord(provider=" ", identifier="id", name="name")
        with self.assertRaisesRegex(ValueError, "size_bytes"):
            ModelRecord(
                provider="example",
                identifier="id",
                name="name",
                size_bytes=-1,
            )


class ResultAndRegistryTests(unittest.TestCase):
    def test_success_and_failure_are_explicit(self) -> None:
        success = OperationResult.success(("value",))
        failure: OperationResult[str] = OperationResult.failure(
            CheckerError(ErrorCode.PROVIDER_ERROR, "failed")
        )

        self.assertTrue(success.succeeded)
        self.assertEqual(success.value, ("value",))
        self.assertFalse(failure.succeeded)
        self.assertEqual(failure.errors[0].to_dict()["code"], "provider_error")

    def test_empty_registry_returns_structured_unavailable_error(self) -> None:
        result = ProviderRegistry().list_models("ollama")

        self.assertFalse(result.succeeded)
        self.assertEqual(
            result.errors[0].to_dict(),
            {
                "code": "provider_unavailable",
                "message": "Provider 'ollama' is not registered.",
                "provider": "ollama",
            },
        )

if __name__ == "__main__":
    unittest.main()
