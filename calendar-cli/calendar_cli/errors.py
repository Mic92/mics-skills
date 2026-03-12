"""Error hierarchy for calendar-cli.

All user-facing errors inherit from ``CalendarCliError`` so the top-level
CLI can catch them in one place and print a clean message without a
traceback.
"""

from __future__ import annotations


class CalendarCliError(Exception):
    """Base for all calendar-cli errors that should produce a clean message."""


class ConfigError(CalendarCliError):
    """Invalid or missing configuration."""


class EventNotFoundError(CalendarCliError):
    """Referenced event UID does not exist."""


class CalendarNotFoundError(CalendarCliError):
    """Referenced calendar directory does not exist."""


class InvalidInputError(CalendarCliError):
    """User-provided input is invalid (bad date, email, regex, etc.)."""


class ParseError(CalendarCliError):
    """Failed to parse calendar/email data."""


class SendError(CalendarCliError):
    """Failed to send email via msmtp."""
