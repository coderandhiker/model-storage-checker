"""Errors raised by providers and provider selection."""


class ModelStorageCheckerError(Exception):
    """Base class for expected checker failures."""


class UnsupportedProviderError(ModelStorageCheckerError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"Provider {provider!r} is not supported")


class ProviderUnavailableError(ModelStorageCheckerError):
    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"Provider {provider!r} is unavailable: {reason}")


class UnsupportedOperationError(ModelStorageCheckerError):
    def __init__(self, provider: str, operation: str) -> None:
        self.provider = provider
        self.operation = operation
        super().__init__(
            f"Provider {provider!r} does not support operation {operation!r}"
        )


class ProviderFailureError(ModelStorageCheckerError):
    def __init__(self, provider: str, operation: str, reason: str) -> None:
        self.provider = provider
        self.operation = operation
        self.reason = reason
        super().__init__(
            f"Provider {provider!r} failed operation {operation!r}: {reason}"
        )
