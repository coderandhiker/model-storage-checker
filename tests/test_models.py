import unittest

from model_storage_checker.models import (
    ModelRecord,
    Operation,
    ProviderResult,
    ProviderStatus,
)


class ModelRecordTests(unittest.TestCase):
    def test_record_is_validated_and_serialized_deterministically(self) -> None:
        record = ModelRecord(
            provider="test",
            model_id="model-b",
            size_bytes=42,
            attributes={"z": "last", "a": "first"},
        )

        self.assertEqual(list(record.attributes), ["a", "z"])
        self.assertEqual(
            record.to_dict(),
            {
                "attributes": {"a": "first", "z": "last"},
                "location": None,
                "model_id": "model-b",
                "provider": "test",
                "size_bytes": 42,
            },
        )

    def test_negative_size_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            ModelRecord(provider="test", model_id="model", size_bytes=-1)


class ProviderResultTests(unittest.TestCase):
    def test_success_orders_records(self) -> None:
        records = (
            ModelRecord(provider="test", model_id="z"),
            ModelRecord(provider="test", model_id="a"),
        )

        result = ProviderResult.success("test", Operation.LIST, records)

        self.assertEqual([record.model_id for record in result.records], ["a", "z"])

    def test_failure_requires_non_ok_status(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be ok"):
            ProviderResult.failure("test", Operation.LIST, ProviderStatus.OK, "bad")

if __name__ == "__main__":
    unittest.main()
    unittest.main()
