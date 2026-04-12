"""Custom exceptions for buildbot-pr-check."""


class BuildbotCheckError(Exception):
    """Base exception for buildbot-pr-check errors."""


class InvalidPRURLError(BuildbotCheckError):
    """Raised when PR URL is invalid or unsupported."""


class APIError(BuildbotCheckError):
    """Raised when API calls fail."""


class BuildbotAPIError(APIError):
    """Raised when Buildbot API calls fail."""


class GitHubAPIError(APIError):
    """Raised when GitHub API calls fail."""


class GiteaAPIError(APIError):
    """Raised when Gitea API calls fail."""
