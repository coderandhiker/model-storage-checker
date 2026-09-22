"""Provider contracts and registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .errors import CheckerError, ErrorCode
from .models import ModelRecord
from .results import OperationResult


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """Current provider availability."""

    name: str
    available: bool
    message: str | None = None

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "name": self.name,
            "available": self.available,
            "message": self.message,
        }


class ModelProvider(ABC):
    """Interface implemented by model storage providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable provider name."""

    @abstractmethod
    def status(self) -> ProviderStatus:
        """Report whether provider operations are currently available."""

    @abstractmethod
    def list_models(self) -> OperationResult[tuple[ModelRecord, ...]]:
        """Return model artifacts known to this provider."""


class ProviderRegistry:
    """Collection of provider implementations available to the CLI."""

    def __init__(self, providers: tuple[ModelProvider, ...] = ()) -> None:
        self._providers: dict[str, ModelProvider] = {}
        for provider in providers:
            if provider.name in self._providers:
                raise ValueError(f"duplicate provider: {provider.name}")
            self._providers[provider.name] = provider

    def statuses(self) -> tuple[ProviderStatus, ...]:
        return tuple(
            self._providers[name].status() for name in sorted(self._providers)
        )

    @property
    def names(self) -> tuple[str, ...]:
        """Return registered provider names in stable order."""

        return tuple(sorted(self._providers))

    def list_models(
        self, provider_name: str
    ) -> OperationResult[tuple[ModelRecord, ...]]:
        provider = self._providers.get(provider_name)
        if provider is None:
            return OperationResult.failure(
                CheckerError(
                    code=ErrorCode.PROVIDER_UNAVAILABLE,
                    message=f"Provider '{provider_name}' is not registered.",
                    provider=provider_name,
                )
            )

        status = provider.status()
        if not status.available:
            return OperationResult.failure(
                CheckerError(
                    code=ErrorCode.PROVIDER_UNAVAILABLE,
                    message=status.message
                    or f"Provider '{provider_name}' is unavailable.",
                    provider=provider_name,
                )
            )
        return provider.list_models()
