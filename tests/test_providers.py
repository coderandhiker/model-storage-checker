import unittest

from model_storage_checker.errors import UnsupportedProviderError
from model_storage_checker.models import Operation, ProviderResult
from model_storage_checker.providers import ProviderRegistry


class StubProvider:
    name = "stub"

    def run(self, operation: Operation) -> ProviderResult:
        return ProviderResult.success(self.name, operation)


class ProviderRegistryTests(unittest.TestCase):
    def test_names_are_sorted(self) -> None:
        registry = ProviderRegistry(
            (StubProvider(),), unsupported_names=("z-provider", "a-provider")
        )

        self.assertEqual(registry.names, ("a-provider", "stub", "z-provider"))

    def test_registered_provider_runs(self) -> None:
        registry = ProviderRegistry((StubProvider(),))

        result = registry.run("stub", Operation.LIST)

        self.assertEqual(result, ProviderResult.success("stub", Operation.LIST))

    def test_unknown_or_declared_unsupported_provider_is_explicit(self) -> None:
        registry = ProviderRegistry(unsupported_names=("planned",))

        for provider in ("planned", "unknown"):
            with self.subTest(provider=provider):
                with self.assertRaisesRegex(UnsupportedProviderError, provider):
                    registry.run(provider, Operation.LIST)

if __name__ == "__main__":
    unittest.main()
    unittest.main()
