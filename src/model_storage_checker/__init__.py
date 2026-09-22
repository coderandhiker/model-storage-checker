"""Public abstractions for model storage providers."""

from .errors import (
    ModelStorageCheckerError,
    ProviderFailureError,
    ProviderUnavailableError,
    UnsupportedOperationError,
    UnsupportedProviderError,
)
from .models import ModelRecord, Operation, ProviderResult, ProviderStatus
from .ollama import OllamaConfig, OllamaProvider
from .providers import Provider, ProviderRegistry

__all__ = [
    "ModelRecord",
    "ModelStorageCheckerError",
    "Operation",
    "OllamaConfig",
    "OllamaProvider",
    "Provider",
    "ProviderFailureError",
    "ProviderRegistry",
    "ProviderResult",
    "ProviderStatus",
    "ProviderUnavailableError",
    "UnsupportedOperationError",
    "UnsupportedProviderError",
]
