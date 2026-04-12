"""URL parsing for PR URLs and buildbot web URLs."""

import re
import urllib.parse
from dataclasses import dataclass

from .exceptions import InvalidPRURLError


@dataclass
class PRInfo:
    platform: str  # "github" | "gitea"
    host: str  # forge hostname
    owner: str
    repo: str
    pr_num: str


@dataclass
class BuildbotRef:
    """Reference into a buildbot instance parsed from a web (#/...) URL."""

    base_url: str  # https://host
    builder_id: int | None = None
    build_num: int | None = None


def is_safe_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme == "https" and bool(parsed.netloc)
    except (ValueError, AttributeError):
        return False


def get_pr_info(pr_url: str) -> PRInfo:
    """Extract platform/host/owner/repo/pr_num from a GitHub or Gitea PR URL."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if m:
        return PRInfo("github", "github.com", m.group(1), m.group(2), m.group(3))

    m = re.match(r"https://([^/]+)/([^/]+)/([^/]+)/pulls/(\d+)", pr_url)
    if m:
        return PRInfo("gitea", m.group(1), m.group(2), m.group(3), m.group(4))

    raise InvalidPRURLError(f"Invalid PR URL: {pr_url}. Supported: GitHub and Gitea")


def parse_buildbot_url(url: str) -> BuildbotRef:
    """Parse a buildbot web URL into a :class:`BuildbotRef`.

    Understands ``https://bb/#/builders/19/builds/2785`` (used by forge commit
    statuses); other shapes return only ``base_url``.
    """
    p = urllib.parse.urlparse(url)
    if not p.scheme or not p.netloc:
        raise InvalidPRURLError(f"Not a buildbot URL: {url}")
    base = f"{p.scheme}://{p.netloc}"
    frag = p.fragment or p.path  # tolerate URLs without the '#'

    ref = BuildbotRef(base_url=base)
    m = re.search(r"/builders/(\d+)/builds/(\d+)", frag)
    if m:
        ref.builder_id = int(m.group(1))
        ref.build_num = int(m.group(2))
    return ref
