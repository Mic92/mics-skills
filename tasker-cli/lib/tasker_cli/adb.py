"""ADB broadcast wrapper for triggering Tasker tasks."""

from __future__ import annotations

import subprocess


class AdbError(Exception):
    """Error running adb commands."""


def trigger_task(
    task_name: str,
    *,
    par1: str | None = None,
    par2: str | None = None,
    adb_target: str | None = None,
) -> None:
    """Trigger a named Tasker task via adb broadcast.

    Args:
        task_name: The name of the task to trigger.
        par1: Optional parameter 1.
        par2: Optional parameter 2.
        adb_target: Optional host:port for adb -s flag.
    """
    cmd: list[str] = ["adb"]

    if adb_target:
        cmd.extend(["-s", adb_target])

    cmd.extend(
        [
            "shell",
            "am",
            "broadcast",
            "-a",
            "net.dinglisch.android.taskerm.ACTION_TASK",
            "-es",
            "task_name",
            task_name,
        ]
    )

    if par1 is not None:
        cmd.extend(["-es", "par1", par1])
    if par2 is not None:
        cmd.extend(["-es", "par2", par2])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except FileNotFoundError as e:
        msg = "adb not found. Install android-tools."
        raise AdbError(msg) from e
    except subprocess.TimeoutExpired as e:
        msg = "adb command timed out"
        raise AdbError(msg) from e

    if result.returncode != 0:
        msg = f"adb broadcast failed: {result.stderr.strip()}"
        raise AdbError(msg)

    print(f"✓ Triggered task: {task_name}")
    if result.stdout.strip():
        print(result.stdout.strip())
