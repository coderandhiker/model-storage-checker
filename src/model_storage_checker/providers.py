"""Provider protocol and registry."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from .errors import UnsupportedProviderError
from .models import Operation, ProviderResult


@runtime_checkable
class Provider(Protocol):
    @property
    def name(self) -> str:
        """Return the stable command-line name for this provider."""

    def run(self, operation: Operation) -> ProviderResult:
        """Run a read-only provider operation."""


class ProviderRegistry:
    def __init__(
        self,
        providers: Iterable[Provider] = (),
        *,
        unsupported_names: Iterable[str] = (),
    ) -> None:
        self._providers: dict[str, Provider] = {}
        for provider in providers:
            if provider.name in self._providers:
                raise ValueError(f"Duplicate provider name: {provider.name!r}")
            self._providers[provider.name] = provider

        unsupported = set(unsupported_names)
        overlap = self._providers.keys() & unsupported
        if overlap:
            name = sorted(overlap)[0]
            raise ValueError(f"Provider cannot also be unsupported: {name!r}")
        self._unsupported_names = frozenset(unsupported)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted((*self._providers, *self._unsupported_names)))

    def run(self, provider_name: str, operation: Operation) -> ProviderResult:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise UnsupportedProviderError(provider_name)
        return provider.run(operation)


DEFAULT_REGISTRY = ProviderRegistry(
    unsupported_names=("docker", "lm-studio", "ollama")
)
