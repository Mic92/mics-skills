"""Shared utilities used across calendar-cli modules."""

from __future__ import annotations

import email as email_lib
import email.utils
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from icalendar import Calendar, Timezone

if TYPE_CHECKING:
    from icalendar import Event, vCalAddress


def strip_mailto(s: str) -> str:
    """Remove the mailto: prefix from a calendar address string.

    Calendar producers use both ``MAILTO:`` and ``mailto:``; handle both.
    """
    return s.replace("MAILTO:", "").replace("mailto:", "")


def get_attendee_list(component: Event) -> list[vCalAddress]:
    """Return the ATTENDEE property as a list, even if there's only one."""
    raw = component.get("attendee")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [raw]
    return raw


def new_calendar(*, method: str | None = None) -> Calendar:
    """Create a VCALENDAR with the standard calendar-cli headers.

    Optionally sets the METHOD property (e.g. REQUEST, REPLY, CANCEL).
    """
    cal = Calendar()
    cal.add("prodid", "-//calendar-cli//mics-skills//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    if method:
        cal.add("method", method)
    return cal


def parse_rrule_string(rrule: str) -> dict[str, Any]:
    """Parse an iCalendar RRULE string like ``FREQ=WEEKLY;COUNT=10`` into a dict.

    Handles special value types that icalendar expects:
    - UNTIL with a ``Z`` suffix is converted to a UTC datetime
    - BYDAY comma-separated values are split into a list
    """
    parts: dict[str, Any] = {}
    for segment in rrule.split(";"):
        if "=" not in segment:
            continue
        k, v = segment.split("=", 1)
        if k == "UNTIL" and v.endswith("Z"):
            parts[k] = datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        elif k == "BYDAY":
            parts[k] = [day.strip() for day in v.split(",")]
        else:
            parts[k] = v
    return parts


def add_vtimezones(cal: Calendar, *dts: datetime | date) -> None:
    """Add VTIMEZONE components for any Olson timezones referenced by the datetimes.

    RFC 5545 §3.6.5 requires a VTIMEZONE for every TZID referenced in
    the calendar object.  Uses icalendar's Timezone.from_tzinfo() to
    generate standard-compliant VTIMEZONE definitions.
    """
    seen: set[str] = set()
    for dt in dts:
        if not isinstance(dt, datetime) or dt.tzinfo is None:
            continue
        tzname = str(dt.tzinfo)
        # Skip UTC (no VTIMEZONE needed) and duplicates
        if tzname in seen or tzname in ("UTC", "utc"):
            continue
        seen.add(tzname)
        try:
            vtz = Timezone.from_tzinfo(dt.tzinfo)
            cal.add_component(vtz)
        except (KeyError, ValueError):
            # Not all tzinfo objects can be converted; skip gracefully
            pass


def extract_calendar_parts_from_email(content: bytes) -> list[bytes]:
    """Extract raw calendar data from a MIME email message.

    A MIME part can match by content-type (text/calendar, application/ics)
    **or** by filename (*.ics).  Each part is only added once even if it
    matches both criteria.
    """
    msg = email_lib.message_from_bytes(content)
    calendars: list[bytes] = []

    for part in msg.walk():
        if part.get_content_type() in ["text/calendar", "application/ics"]:
            cal_data = part.get_payload(decode=True)
            if isinstance(cal_data, bytes) and b"BEGIN:VCALENDAR" in cal_data:
                calendars.append(cal_data)
                continue  # Don't also check filename for this part
        # Also check for .ics attachments (fallback for unknown content-type)
        filename = part.get_filename()
        if filename and filename.lower().endswith(".ics"):
            cal_data = part.get_payload(decode=True)
            if isinstance(cal_data, bytes) and b"BEGIN:VCALENDAR" in cal_data:
                calendars.append(cal_data)

    return calendars


def extract_recipient_email(content: str | bytes) -> str | None:
    """Extract the To: email address from an email message."""
    if isinstance(content, bytes):
        msg = email_lib.message_from_bytes(content)
    else:
        msg = email_lib.message_from_string(content)
    if "To" in msg:
        _name, addr = email.utils.parseaddr(msg["To"])
        if addr:
            return addr
    return None
