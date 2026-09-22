"""Public abstractions for model storage providers."""

from .docker import DockerConfig, DockerProvider
from .errors import (
    ModelStorageCheckerError,
    ProviderFailureError,
    ProviderUnavailableError,
    UnsupportedOperationError,
    UnsupportedProviderError,
)
from .lm_studio import LMStudioConfig, LMStudioProvider
from .models import ModelRecord, Operation, ProviderResult, ProviderStatus
from .ollama import OllamaConfig, OllamaProvider
from .providers import Provider, ProviderRegistry
from .reporting import (
    CleanupCandidate,
    StorageSummary,
    StorageTotal,
    build_summary,
    find_cleanup_candidates,
)

__all__ = [
    "DockerConfig",
    "DockerProvider",
    "CleanupCandidate",
    "ModelRecord",
    "ModelStorageCheckerError",
    "LMStudioConfig",
    "LMStudioProvider",
    "Operation",
    "OllamaConfig",
    "OllamaProvider",
    "Provider",
    "ProviderFailureError",
    "ProviderRegistry",
    "ProviderResult",
    "ProviderStatus",
    "ProviderUnavailableError",
    "StorageSummary",
    "StorageTotal",
    "UnsupportedOperationError",
    "UnsupportedProviderError",
    "build_summary",
    "find_cleanup_candidates",
]
