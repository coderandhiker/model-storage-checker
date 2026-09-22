"""Model storage checker foundation."""

from .errors import CheckerError, ErrorCode
from .lm_studio import LMStudioProvider
from .models import ModelRecord
from .ollama import OllamaProvider
from .providers import ModelProvider, ProviderRegistry, ProviderStatus
from .results import OperationResult

__all__ = [
    "CheckerError",
    "ErrorCode",
    "LMStudioProvider",
    "ModelProvider",
    "ModelRecord",
    "OllamaProvider",
    "OperationResult",
    "ProviderRegistry",
    "ProviderStatus",
]

__version__ = "0.1.0"
