"""Browsh backend management for headless browser operation.

Starts browsh with a Firefox/LibreWolf backend when no browser is running,
providing browser-cli functionality without a GUI browser.
"""

import logging
import os
import pty
import shlex
import shutil
import signal
import time
from pathlib import Path

from browser_cli.config import get_firefox_path
from browser_cli.paths import get_socket_path

logger = logging.getLogger(__name__)

_PID_FILE_NAME = "browsh.pid"


def _get_pid_path() -> Path:
    """Get path to browsh PID file, colocated with the socket."""
    return get_socket_path().parent / _PID_FILE_NAME


def _find_firefox_wrapper(firefox_path: str) -> str:
    """Create a wrapper script if firefox_path contains spaces.

    Browsh has a bug where it splits --firefox.path at spaces when
    calling the binary with --version. Work around by creating a
    wrapper script in XDG_RUNTIME_DIR or cache dir.
    """
    if " " not in firefox_path:
        return firefox_path

    wrapper_dir = get_socket_path().parent
    wrapper_path = wrapper_dir / "firefox-wrapper"

    wrapper_content = f"""#!/usr/bin/env bash
exec {shlex.quote(firefox_path)} "$@"
"""
    wrapper_path.write_text(wrapper_content)
    wrapper_path.chmod(0o755)
    return str(wrapper_path)


def _build_browsh_cmd(firefox_path: str | None) -> list[str]:
    """Build the browsh command with appropriate arguments."""
    browsh_bin = shutil.which("browsh")
    if not browsh_bin:
        msg = (
            "browsh not found in PATH. Install browsh to use headless mode.\n"
            "See: https://www.brow.sh/docs/installation/"
        )
        raise FileNotFoundError(msg)

    cmd = [browsh_bin, "--startup-url", "about:blank"]
    if firefox_path:
        wrapper_path = _find_firefox_wrapper(firefox_path)
        cmd.extend(["--firefox.path", wrapper_path])
    return cmd


def _spawn_browsh(cmd: list[str]) -> int:
    """Fork browsh with a PTY and return the child PID.

    Browsh requires a TTY on stdin to start. We allocate a PTY pair
    manually and double-fork so the intermediate parent can exit
    immediately, detaching browsh from the CLI process.

    Previously we used pty.fork() with a daemon drain thread, but once
    the CLI process exited the master fd closed and subsequent writes
    from browsh hit EIO, killing the TUI renderer. Keeping the master
    fd alive inside the detached child avoids that, and redirecting
    stdout/stderr to /dev/null means nothing ever reads the PTY so it
    cannot fill up.
    """
    master_fd, slave_fd = pty.openpty()

    pid = os.fork()
    if pid == 0:
        # Child: new session so we get our own process group for
        # killpg() in stop(), and so the PTY becomes our ctty.
        os.setsid()
        signal.signal(signal.SIGHUP, signal.SIG_IGN)

        # stdin from PTY slave (browsh checks isatty on stdin),
        # stdout/stderr to /dev/null so the PTY buffer never fills.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(slave_fd, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(slave_fd)
        os.close(devnull)
        # Keep master_fd open so the slave stays valid after the
        # spawning CLI process exits.

        os.execvp(cmd[0], cmd)  # noqa: S606

    # Parent: close both ends, we don't need them.
    os.close(master_fd)
    os.close(slave_fd)
    return pid


def _wait_for_socket(child_pid: int, timeout: float) -> None:
    """Wait for the browser-cli socket to appear, or raise on failure."""
    socket_path = get_socket_path()
    pid_path = _get_pid_path()
    start_time = time.monotonic()

    while time.monotonic() - start_time < timeout:
        # Check if browsh died
        pid_result, status = os.waitpid(child_pid, os.WNOHANG)
        if pid_result != 0:
            pid_path.unlink(missing_ok=True)
            exit_code = os.waitstatus_to_exitcode(status)
            msg = f"Browsh exited with code {exit_code}"
            raise RuntimeError(msg)

        if socket_path.exists():
            logger.info("Browsh backend started (PID %d)", child_pid)
            return

        time.sleep(0.5)

    # Timeout — clean up
    stop()
    msg = f"Timed out after {timeout}s waiting for browser-cli socket"
    raise TimeoutError(msg)


def is_running() -> bool:
    """Check if a browsh backend is currently running."""
    pid_path = _get_pid_path()
    if not pid_path.exists():
        return False

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
    except (ValueError, ProcessLookupError, PermissionError):
        pid_path.unlink(missing_ok=True)
        return False
    else:
        return True


def start(firefox_path: str | None = None, timeout: float = 30.0) -> None:
    """Start browsh as a headless browser backend.

    Launches browsh with a PTY in the background. The browser-cli
    extension inside browsh's Firefox will create the native messaging
    bridge and socket.

    Args:
        firefox_path: Path to Firefox/LibreWolf binary. If None, uses
            config file or browsh's default.
        timeout: Seconds to wait for the socket to appear.

    Raises:
        FileNotFoundError: If browsh is not installed.
        TimeoutError: If the socket doesn't appear within timeout.
        RuntimeError: If browsh exits unexpectedly.

    """
    if is_running():
        logger.debug("Browsh backend already running")
        return

    if firefox_path is None:
        firefox_path = get_firefox_path()

    cmd = _build_browsh_cmd(firefox_path)

    # Clean up stale socket and pid file
    get_socket_path().unlink(missing_ok=True)
    _get_pid_path().unlink(missing_ok=True)

    child_pid = _spawn_browsh(cmd)

    # Save PID for is_running() and stop()
    _get_pid_path().write_text(str(child_pid))

    _wait_for_socket(child_pid, timeout)


def stop() -> None:
    """Stop the browsh backend if running."""
    pid_path = _get_pid_path()
    if not pid_path.exists():
        return

    try:
        pid = int(pid_path.read_text().strip())
        # Send SIGTERM to the process group (kills browsh + firefox)
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        logger.info("Stopped browsh backend (PID %d)", pid)
    except (ValueError, ProcessLookupError, PermissionError):
        pass
    finally:
        pid_path.unlink(missing_ok=True)
        get_socket_path().unlink(missing_ok=True)
