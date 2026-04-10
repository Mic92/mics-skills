"""GitHub API helpers (stdlib only)."""

import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from typing import Any

from .exceptions import GitHubAPIError
from .url_parser import is_safe_url

logger = logging.getLogger(__name__)


def get_github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
        token = result.stdout.strip()
        if token:
            return token
    except subprocess.CalledProcessError as e:
        logger.debug(f"gh CLI not authenticated: {e}")
    except FileNotFoundError:
        logger.debug("gh CLI not found")
    return None


def _gh_get(url: str) -> Any:
    req = urllib.request.Request(url)  # noqa: S310
    req.add_header("Accept", "application/vnd.github.v3+json")
    token = get_github_token()
    if token:
        req.add_header("Authorization", f"token {token}")
    with urllib.request.urlopen(req) as response:  # noqa: S310
        return json.loads(response.read())


def get_pr_head_sha(owner: str, repo: str, pr_num: str) -> str:
    try:
        data = _gh_get(f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}")
        return str(data["head"]["sha"])
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        msg = f"Failed to fetch PR data from GitHub: {e}"
        raise GitHubAPIError(msg) from e
    except (json.JSONDecodeError, KeyError) as e:
        msg = f"Failed to parse GitHub PR response: {e}"
        raise GitHubAPIError(msg) from e


def get_buildbot_urls_from_github(owner: str, repo: str, head_sha: str) -> list[str]:
    """Find buildbot build URLs from GitHub check-runs / commit statuses for the head SHA."""
    urls: set[str] = set()

    try:
        data = _gh_get(f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/check-runs")
        for check in data.get("check_runs", []):
            name = check.get("name", "").lower()
            app = check.get("app", {}).get("name", "").lower()
            details = check.get("details_url", "")
            if ("buildbot" in name or "buildbot" in app) and is_safe_url(details):
                urls.add(details)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        pass

    try:
        data = _gh_get(f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/status")
        for status in data.get("statuses", []):
            target = status.get("target_url", "")
            if "buildbot" in status.get("context", "").lower() and is_safe_url(target):
                urls.add(target)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        pass

    return sorted(urls)
