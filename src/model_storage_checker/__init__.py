"""Model storage checker foundation."""

from .errors import CheckerError, ErrorCode
from .models import ModelRecord
from .ollama import OllamaProvider
from .providers import ModelProvider, ProviderRegistry, ProviderStatus
from .results import OperationResult

__all__ = [
    "CheckerError",
    "ErrorCode",
    "ModelProvider",
    "ModelRecord",
    "OllamaProvider",
    "OperationResult",
    "ProviderRegistry",
    "ProviderStatus",
]

__version__ = "0.1.0"
