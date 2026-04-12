"""Gitea API helpers (stdlib only)."""

import json
import urllib.error
import urllib.request
from typing import Any

from .exceptions import GiteaAPIError
from .url_parser import is_safe_url


def _get(url: str) -> Any:
    req = urllib.request.Request(url)  # noqa: S310
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req) as response:  # noqa: S310
        return json.loads(response.read())


def get_pr_head_sha(host: str, owner: str, repo: str, pr_num: str) -> str:
    try:
        data = _get(f"https://{host}/api/v1/repos/{owner}/{repo}/pulls/{pr_num}")
        return str(data["head"]["sha"])
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        msg = f"Failed to fetch PR data from Gitea: {e}"
        raise GiteaAPIError(msg) from e
    except (json.JSONDecodeError, KeyError) as e:
        msg = f"Failed to parse Gitea PR response: {e}"
        raise GiteaAPIError(msg) from e


def get_buildbot_urls_from_gitea(host: str, owner: str, repo: str, head_sha: str) -> list[str]:
    urls: set[str] = set()
    try:
        statuses = _get(f"https://{host}/api/v1/repos/{owner}/{repo}/statuses/{head_sha}")
        for status in statuses:
            target = status.get("target_url", "")
            if "buildbot" in status.get("context", "").lower() and is_safe_url(target):
                urls.add(target)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        pass
    return sorted(urls)
