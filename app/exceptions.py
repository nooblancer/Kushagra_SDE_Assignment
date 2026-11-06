from typing import Any, Optional


class PortalError(Exception):
    """Base exception for all portal-related errors."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class PortalAuthError(PortalError):
    """Raised when authentication against Urja Ops fails or session expires."""
    pass


class PortalNotFoundError(PortalError):
    """Raised when a requested resource (meter, reading, etc.) is not found upstream."""
    pass


class PortalRateLimitError(PortalError):
    """Raised when the upstream portal is rate limiting requests."""
    pass


class PortalUpstreamError(PortalError):
    """Raised when an unrecoverable or unexpected error occurs communicating with Urja Ops."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Any] = None) -> None:
        super().__init__(message, details)
        self.status_code = status_code

