"""buildbot-pr-check - Inspect Buildbot (buildbot-nix) CI for a PR."""

from .build_status import BuildStatus, get_build_status
from .cli import main
from .exceptions import (
    APIError,
    BuildbotAPIError,
    BuildbotCheckError,
    GiteaAPIError,
    GitHubAPIError,
    InvalidPRURLError,
)

__version__ = "0.2.0"

__all__ = [
    "APIError",
    "BuildStatus",
    "BuildbotAPIError",
    "BuildbotCheckError",
    "GiteaAPIError",
    "GitHubAPIError",
    "InvalidPRURLError",
    "get_build_status",
    "main",
]
