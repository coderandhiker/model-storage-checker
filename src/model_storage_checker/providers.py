"""Provider protocol and registry."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from .errors import UnsupportedProviderError
from .models import Operation, ProviderResult
from .ollama import OllamaConfig, OllamaProvider


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


def create_default_registry(
    *,
    ollama_base_url: str | None = None,
    ollama_timeout: float | None = None,
) -> ProviderRegistry:
    defaults = OllamaConfig()
    config = OllamaConfig(
        base_url=ollama_base_url or defaults.base_url,
        timeout=ollama_timeout if ollama_timeout is not None else defaults.timeout,
    )
    return ProviderRegistry(
        (OllamaProvider(config),),
        unsupported_names=("docker", "lm-studio"),
    )


DEFAULT_REGISTRY = create_default_registry()
