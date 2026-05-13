"""Shared Kagi auth — config, token resolution, authenticated cookie session."""

from __future__ import annotations

import json
import subprocess
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, OpenerDirector, Request, build_opener

CONFIG_PATH = Path.home() / ".config" / "kagi" / "config.json"
BASE_URL = "https://kagi.com"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_CONFIG: dict[str, Any] = {
    "password_command": "rbw get kagi-session-link",
    "timeout": 30,
    "max_retries": 5,
}


class KagiError(Exception):
    """Domain error from any kagi flow; cli.py catches and prints."""


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Read the kagi config, writing defaults on first run."""
    config_file = path or CONFIG_PATH
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
        print(f"created default config at {config_file}", file=sys.stderr)
        return dict(DEFAULT_CONFIG)
    loaded: dict[str, Any] = json.loads(config_file.read_text())
    return loaded


def get_session_token(config: dict[str, Any]) -> str:
    """Run ``password_command`` and return a session token.

    Accepts a raw token or a Kagi session-link URL (``?...token=X...``).
    """
    cmd = config.get("password_command", DEFAULT_CONFIG["password_command"])
    # Using shell=True is intentional - password_command comes from the user's
    # config file (matches context7-cli's get_api_key_from_command). Pipelines
    # like `pass show foo | head -1` are common for password-store setups.
    result = subprocess.run(  # noqa: S602
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise KagiError(f"password_command failed: {result.stderr.strip()}")
    raw = result.stdout.strip()
    if not raw:
        raise KagiError("password_command returned empty output")
    if "token=" in raw:
        return raw.split("token=", 1)[1].split("&", 1)[0]
    return raw


def build_opener_authed(
    token: str,
    user_agent: str | None = None,
    timeout: int = 30,
) -> OpenerDirector:
    """Authenticate against Kagi and return an opener with session cookies set."""
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    auth_url = f"{BASE_URL}/html/search?token={token}"
    req = Request(auth_url, headers={"User-Agent": user_agent or USER_AGENT})
    try:
        resp = opener.open(req, timeout=timeout)
    except (HTTPError, URLError) as e:
        msg = f"auth failed: {e}"
        raise KagiError(msg) from e
    final = resp.geturl()
    if "/signin" in final or "/welcome" in final:
        msg = f"token rejected (redirected to {final})"
        raise KagiError(msg)
    return opener


def authed_opener(path: Path | None = None) -> OpenerDirector:
    """Convenience: load config, resolve token, return an authed opener."""
    config = load_config(path)
    timeout_val = config.get("timeout", 30)
    timeout = int(timeout_val) if isinstance(timeout_val, (int, str)) else 30
    return build_opener_authed(get_session_token(config), timeout=timeout)
