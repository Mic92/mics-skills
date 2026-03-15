"""Custom error types for user-facing messages."""

from http import HTTPStatus

# Extra hints for status codes where the standard phrase isn't enough.
_HINTS: dict[int, str] = {
    401: "check your API key",
    403: "insufficient permissions",
}


class CLIError(Exception):
    """Base for all errors that should be shown to the user and exit 1."""


class InputError(CLIError):
    """Bad user-supplied input (file not found, invalid JSON, bad option)."""


class APIError(CLIError):
    """Error returned by the n8n API."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        try:
            phrase = HTTPStatus(status).phrase
        except ValueError:
            phrase = f"HTTP {status}"
        hint = _HINTS.get(status)
        label = f"{phrase} ({hint})" if hint else phrase
        super().__init__(f"{label}: {message}" if message else label)


class ConnectionError_(CLIError):
    """Cannot reach the n8n instance."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Cannot connect to n8n: {reason}")


class ConfigError(CLIError):
    """Missing or invalid configuration."""
