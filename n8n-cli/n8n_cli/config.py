"""Configuration loading and credential resolution."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "n8n-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration from JSON file.

    Config file (~/.config/n8n-cli/config.json):
    {
        "api_url": "https://your-n8n.example.com",
        "api_key": "your-api-key",
        "api_key_command": "rbw get n8n-api-key",
        "api_url_command": "rbw get n8n-api-url",
        "timeout": 30
    }
    """
    path = Path(config_path) if config_path else CONFIG_FILE
    if not path.exists():
        return {}
    try:
        with path.open() as f:
            result: dict[str, Any] = json.load(f)
            return result
    except json.JSONDecodeError as e:
        print(f"Warning: invalid JSON in config file {path}: {e}", file=sys.stderr)
        return {}


def run_secret_command(command: str) -> str | None:
    """Execute a shell command to retrieve a secret value."""
    try:
        result = subprocess.run(  # noqa: S602
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return result.stdout.strip() or None
    except subprocess.TimeoutExpired:
        print(f"Warning: command timed out after 30s: {command}", file=sys.stderr)
        return None
    except subprocess.CalledProcessError as e:
        print(f"Warning: command failed: {command}: {e}", file=sys.stderr)
        if e.stderr:
            print(f"  stderr: {e.stderr.strip()}", file=sys.stderr)
        return None


def _resolve_value(
    env_var: str,
    cfg: dict[str, Any],
    command_key: str,
    direct_key: str,
) -> str | None:
    """Resolve a value from env var > config command > config direct."""
    value = os.environ.get(env_var)
    if value:
        return value

    cmd = cfg.get(command_key)
    if isinstance(cmd, str) and cmd:
        value = run_secret_command(cmd)
        if value:
            return value

    direct = cfg.get(direct_key)
    if isinstance(direct, str) and direct:
        return direct

    return None


def _resolve_timeout(cfg: dict[str, Any]) -> int:
    """Resolve timeout from env > config > default(30)."""
    timeout = 30
    timeout_str = os.environ.get("N8N_API_TIMEOUT")
    if timeout_str:
        try:
            timeout = int(timeout_str)
        except ValueError:
            print(
                f"Warning: invalid N8N_API_TIMEOUT={timeout_str!r}, using default",
                file=sys.stderr,
            )
    elif cfg.get("timeout") is not None:
        try:
            timeout = int(cfg["timeout"])
        except (ValueError, TypeError):
            print(
                f"Warning: invalid timeout in config: {cfg['timeout']!r}, using default",
                file=sys.stderr,
            )
    return timeout


def resolve_credentials(
    config_path: str | None = None,
) -> tuple[str | None, str | None, int]:
    """Resolve API URL, key, and timeout.

    Priority: env vars > config *_command > config direct values.
    """
    cfg = load_config(config_path)
    api_url = _resolve_value("N8N_API_URL", cfg, "api_url_command", "api_url")
    api_key = _resolve_value("N8N_API_KEY", cfg, "api_key_command", "api_key")
    timeout = _resolve_timeout(cfg)
    return api_url, api_key, timeout
