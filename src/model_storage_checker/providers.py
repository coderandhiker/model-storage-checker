"""Provider protocol and registry."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, runtime_checkable

from .docker import DockerConfig, DockerProvider
from .errors import UnsupportedProviderError
from .lm_studio import LMStudioConfig, LMStudioProvider
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
    lm_studio_base_url: str | None = None,
    lm_studio_timeout: float | None = None,
    lm_studio_model_roots: tuple[str, ...] | None = None,
    docker_timeout: float | None = None,
    docker_classify_ai: bool = False,
) -> ProviderRegistry:
    ollama_defaults = OllamaConfig()
    ollama_config = OllamaConfig(
        base_url=ollama_base_url or ollama_defaults.base_url,
        timeout=(
            ollama_timeout if ollama_timeout is not None else ollama_defaults.timeout
        ),
    )
    lm_studio_defaults = LMStudioConfig()
    lm_studio_config = LMStudioConfig(
        base_url=lm_studio_base_url or lm_studio_defaults.base_url,
        timeout=(
            lm_studio_timeout
            if lm_studio_timeout is not None
            else lm_studio_defaults.timeout
        ),
        model_roots=(
            tuple(Path(root) for root in lm_studio_model_roots)
            if lm_studio_model_roots is not None
            else lm_studio_defaults.model_roots
        ),
    )
    docker_defaults = DockerConfig()
    docker_config = DockerConfig(
        timeout=(
            docker_timeout
            if docker_timeout is not None
            else docker_defaults.timeout
        ),
        classify_ai=docker_classify_ai,
    )
    return ProviderRegistry(
        (
            OllamaProvider(ollama_config),
            LMStudioProvider(lm_studio_config),
            DockerProvider(docker_config),
        ),
    )


DEFAULT_REGISTRY = create_default_registry()
