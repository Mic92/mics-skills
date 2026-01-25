"""Path utilities for browser-cli."""

import os
from pathlib import Path


def get_socket_path() -> Path:
    """Get secure socket path for browser-cli.

    Uses XDG_RUNTIME_DIR on Linux, which is:
    - User-owned (mode 0700)
    - Not world-readable
    - Cleared on logout

    On macOS, uses $TMPDIR which is a secure per-user directory
    under /var/folders/ with mode 0700.

    Falls back to XDG_CACHE_HOME/browser-cli/ (~/.cache/browser-cli/)
    with mode 0700 if runtime dir is unavailable.
    """
    # Try XDG_RUNTIME_DIR first (Linux, some macOS setups)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "browser-cli.sock"

    # Fallback: use XDG_CACHE_HOME/browser-cli/ with restrictive permissions
    cache_home = os.environ.get("XDG_CACHE_HOME")
    if not cache_home:
        cache_home = str(Path.home() / ".cache")
    fallback_dir = Path(cache_home) / "browser-cli"
    fallback_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Ensure restrictive permissions even if directory existed
    fallback_dir.chmod(0o700)
    return fallback_dir / "browser-cli.sock"
