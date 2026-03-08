"""Configuration management for browser-cli."""

import os
import tomllib
from pathlib import Path
from typing import Any


def get_config_dir() -> Path:
    """Get XDG-compliant config directory."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        config_dir = Path(xdg_config) / "browser-cli"
    else:
        config_dir = Path.home() / ".config" / "browser-cli"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Get path to config file."""
    return get_config_dir() / "config.toml"


def load_config() -> dict[str, Any]:
    """Load configuration from config file.

    Returns empty dict if file doesn't exist.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return {}
    with config_path.open("rb") as f:
        result: dict[str, Any] = tomllib.load(f)
        return result


def get_firefox_path() -> str | None:
    """Get configured Firefox/LibreWolf path.

    Checks environment variable first, then config file.
    Returns None if not configured (browsh will use its default).
    """
    env_path = os.environ.get("BROWSER_CLI_FIREFOX_PATH")
    if env_path:
        return env_path

    config = load_config()
    path: str | None = config.get("firefox_path")
    return path
