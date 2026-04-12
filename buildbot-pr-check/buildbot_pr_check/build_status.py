"""Buildbot result-code → status mapping."""

from enum import IntEnum


class BuildStatus(IntEnum):
    """Buildbot numeric result codes.

    https://docs.buildbot.net/latest/developer/results.html
    """

    SUCCESS = 0
    WARNINGS = 1
    FAILURE = 2
    SKIPPED = 3
    EXCEPTION = 4
    RETRY = 5
    CANCELLED = 6

    @property
    def is_bad(self) -> bool:
        return self in (BuildStatus.FAILURE, BuildStatus.EXCEPTION, BuildStatus.CANCELLED)


def get_build_status(result_code: int | None) -> BuildStatus | None:
    """Convert Buildbot numeric result code to BuildStatus, or None for in-progress/unknown."""
    if result_code is None:
        return None
    try:
        return BuildStatus(result_code)
    except ValueError:
        return None


def status_name(result_code: int | None) -> str:
    """Human name for a numeric result code (RUNNING for None)."""
    s = get_build_status(result_code)
    return "RUNNING" if s is None else s.name
