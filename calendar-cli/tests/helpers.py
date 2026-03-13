"""Shared helpers for calendar-cli tests.

Provides ICS builders, email template builders, MIME extraction, and
CLI runner wrappers that eliminate boilerplate across test modules.
"""

from __future__ import annotations

import email as email_lib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from calendar_cli.main import main
from icalendar import Calendar

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


# ---------------------------------------------------------------------------
# ICS builder
# ---------------------------------------------------------------------------


@dataclass
class ICSEvent:
    """Parameters for building a VCALENDAR string.

    *dtstart*/*dtend* are raw iCalendar property values — pass a full
    property line suffix, e.g. ``"20250401T090000Z"`` or
    ``";VALUE=DATE:20250401"``.

    *vevent_lines* are injected inside the VEVENT.
    *vcalendar_lines* are injected inside the VCALENDAR (e.g. METHOD).
    *extra_components* are injected after the VEVENT (e.g. a second VEVENT).
    """

    uid: str
    summary: str
    dtstart: str = "20240320T140000Z"
    dtend: str | None = "20240320T150000Z"
    vevent_lines: Sequence[str] = ()
    vcalendar_lines: Sequence[str] = ()
    extra_components: str = ""


def _format_dt_prop(name: str, value: str) -> str:
    """Format a DTSTART/DTEND property, detecting if a param prefix is present."""
    if ":" in value or ";" in value:
        return f"{name}{value}"
    return f"{name}:{value}"


def make_ics(event: ICSEvent) -> str:
    """Build a minimal VCALENDAR string from an ICSEvent."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//test//test//",
        *event.vcalendar_lines,
        "BEGIN:VEVENT",
        f"UID:{event.uid}",
        f"SUMMARY:{event.summary}",
        _format_dt_prop("DTSTART", event.dtstart),
    ]
    if event.dtend is not None:
        lines.append(_format_dt_prop("DTEND", event.dtend))
    lines.extend(event.vevent_lines)
    lines.append("END:VEVENT")
    if event.extra_components:
        lines.append(event.extra_components)
    lines.append("END:VCALENDAR")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email / MIME template builder
# ---------------------------------------------------------------------------

_EMAIL_INVITE_TEMPLATE = """\
From: sender@example.com
To: {to}
Subject: Meeting Invitation
Content-Type: text/calendar

BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:{uid}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{summary}
ORGANIZER:{organizer}
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:{to}
{extra}END:VEVENT
END:VCALENDAR"""


@dataclass
class EmailInvite:
    """Parameters for building an RFC 822 email with a calendar invite."""

    uid: str = "test@example.com"
    to: str = "attendee@example.com"
    summary: str = "Test Meeting"
    organizer: str = "mailto:organizer@example.com"
    dtstart: str = "20240320T140000Z"
    dtend: str = "20240320T150000Z"
    extra: str = ""


def make_email_invite(invite: EmailInvite) -> str:
    """Build an RFC 822 email with an embedded iCalendar invite."""
    extra = invite.extra
    if extra and not extra.endswith("\n"):
        extra += "\n"
    return _EMAIL_INVITE_TEMPLATE.format(
        uid=invite.uid,
        to=invite.to,
        summary=invite.summary,
        organizer=invite.organizer,
        dtstart=invite.dtstart,
        dtend=invite.dtend,
        extra=extra,
    )


# ---------------------------------------------------------------------------
# MIME / ICS extraction helpers
# ---------------------------------------------------------------------------


def extract_ics_from_email(raw: str) -> Calendar:
    """Parse a raw email string and return the first calendar attachment."""
    msg = email_lib.message_from_string(raw)
    for part in msg.walk():
        ct = part.get_content_type()
        fn = part.get_filename() or ""
        if ct == "text/calendar" or fn.endswith(".ics"):
            payload = part.get_payload(decode=True)
            assert isinstance(payload, bytes)
            cal = Calendar.from_ical(payload.decode())
            assert isinstance(cal, Calendar)
            return cal
    err_msg = "No calendar attachment found in email"
    raise AssertionError(err_msg)


def parse_reply_email(
    raw: str,
) -> tuple[email_lib.message.Message, Calendar]:
    """Parse a reply email and extract the iCalendar attachment."""
    msg = email_lib.message_from_string(raw)
    cal = extract_ics_from_email(raw)
    return msg, cal


# ---------------------------------------------------------------------------
# Store fixture helpers
# ---------------------------------------------------------------------------


def setup_calendar_dir(tmp_path: Path, ics_files: dict[str, dict[str, str]]) -> str:
    """Create a calendar directory tree with ICS files.

    *ics_files* maps ``calendar_name -> {filename: ics_content}``.
    Returns the root calendar directory as a string.
    """
    for cal_name, files in ics_files.items():
        cal_dir = tmp_path / cal_name
        cal_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (cal_dir / filename).write_text(content)
    return str(tmp_path)


def setup_single_calendar(
    tmp_path: Path,
    ics_content: str,
    *,
    calendar: str = "personal",
    filename: str = "event.ics",
) -> str:
    """Create a calendar dir with a single ICS file. Returns cal_dir."""
    return setup_calendar_dir(tmp_path, {calendar: {filename: ics_content}})


# ---------------------------------------------------------------------------
# CLI runner helpers
# ---------------------------------------------------------------------------


def run_cli(cal_dir: str, *args: str) -> int:
    """Run calendar-cli with the given calendar dir (sync is off by default)."""
    return main(["--calendar-dir", cal_dir, *args])


@dataclass
class InviteArgs:
    """Parameters for running the ``invite`` subcommand."""

    summary: str
    attendees: str = "a@b.com"
    organizer: str = "org@example.com"
    start: str = "2024-03-20 14:00"
    timezone: str = "UTC"
    extra_args: Sequence[str] = ()
    output_email: str | None = None
    output_ics: str | None = None


def run_invite(tmp_path: Path, invite: InviteArgs) -> int:
    """Run the ``invite`` subcommand with common defaults."""
    args: list[str] = [
        "invite",
        "-s",
        invite.summary,
        "--start",
        invite.start,
        "--timezone",
        invite.timezone,
        "-a",
        invite.attendees,
        "--organizer-email",
        invite.organizer,
        "--no-local-save",
    ]
    if invite.output_email is not None:
        args.extend(["--output-email", invite.output_email])
    else:
        args.extend(["--output-email", str(tmp_path / "invite.eml")])
    if invite.output_ics is not None:
        args.extend(["--output-ics", invite.output_ics])
    args.extend(invite.extra_args)
    return main(args)
