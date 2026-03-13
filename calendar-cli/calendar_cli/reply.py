"""Reply to calendar invites with RSVP responses."""

from __future__ import annotations

import email.utils
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING

from icalendar import Calendar, Event, vCalAddress, vText

from .config import resolve_user_name
from .errors import InvalidInputError, ParseError, SendError
from .util import (
    extract_calendar_parts_from_email,
    extract_recipient_email,
    get_attendee_list,
    new_calendar,
    strip_mailto,
)

if TYPE_CHECKING:
    import argparse


@dataclass
class ReplyConfig:
    """Configuration for reply command."""

    status: str  # accept, decline, tentative
    file_path: str | None = None
    comment: str | None = None
    dry_run: bool = False
    calendars_dir: str | None = None


def extract_calendar_from_email(
    email_content: str,
) -> tuple[Calendar | None, str | None]:
    """Extract calendar and recipient email from email message.

    Uses the shared ``extract_calendar_parts_from_email`` helper for
    MIME extraction and falls back to parsing the raw content as ICS.
    """
    content_bytes = email_content.encode("utf-8", errors="surrogateescape")
    to_email = extract_recipient_email(content_bytes)

    # Try MIME extraction first
    parts = extract_calendar_parts_from_email(content_bytes)
    for part_data in parts:
        try:
            cal = Calendar.from_ical(part_data)
            if isinstance(cal, Calendar):
                return cal, to_email
        except (ValueError, TypeError):
            continue

    # Fallback: try to parse the raw content as ICS directly
    if "BEGIN:VCALENDAR" in email_content:
        try:
            result = Calendar.from_ical(email_content)
            if isinstance(result, Calendar):
                return result, to_email
        except (ValueError, TypeError):
            pass

    return None, to_email


def create_reply(  # noqa: C901
    original_cal: Calendar,
    status: str,
    user_email: str,
    comment: str | None = None,
) -> Calendar:
    """Create REPLY calendar for RSVP response."""
    reply_cal = new_calendar(method="REPLY")

    user_name = resolve_user_name(user_email)

    # Find the original event
    for component in original_cal.walk():
        if component.name == "VEVENT":
            # Create reply event with minimal required fields
            reply_event = Event()

            # Copy fields relevant to the reply
            for field in ["uid", "sequence", "dtstart", "dtend", "summary"]:
                if field in component:
                    reply_event.add(field, component[field])

            # DTSTAMP is required (RFC 5545 §3.6.1) — always set to now
            reply_event.add("dtstamp", datetime.now(tz=UTC))

            # Copy RECURRENCE-ID so the reply targets the correct
            # instance of a recurring event (RFC 6047 §3.2.3)
            if "recurrence-id" in component:
                reply_event.add("recurrence-id", component["recurrence-id"])

            # Set organizer from original
            if "organizer" in component:
                reply_event.add("organizer", component["organizer"])

            # Find our attendee entry and update status
            found_self = False
            for attendee in get_attendee_list(component):
                attendee_email = strip_mailto(str(attendee)).lower()
                if attendee_email == user_email.lower():
                    # Update our attendance status
                    reply_attendee = vCalAddress(f"mailto:{user_email}")
                    reply_attendee.params["cn"] = vText(user_name)
                    reply_attendee.params["partstat"] = vText(status)
                    reply_attendee.params["rsvp"] = vText("FALSE")
                    if "role" in attendee.params:
                        reply_attendee.params["role"] = attendee.params["role"]
                    reply_event.add("attendee", reply_attendee)
                    found_self = True
                    break

            # If we weren't in the attendee list, add ourselves
            if not found_self:
                reply_attendee = vCalAddress(f"mailto:{user_email}")
                reply_attendee.params["cn"] = vText(user_name)
                reply_attendee.params["partstat"] = vText(status)
                reply_attendee.params["rsvp"] = vText("FALSE")
                reply_attendee.params["role"] = vText("REQ-PARTICIPANT")
                reply_event.add("attendee", reply_attendee)

            # Add comment if provided
            if comment:
                reply_event.add("comment", comment)

            reply_cal.add_component(reply_event)
            break
    else:
        msg = "Original calendar contains no VEVENT"
        raise ParseError(msg)

    return reply_cal


def send_reply(
    reply_cal: Calendar,
    organizer_email: str,
    event_summary: str,
    status: str,
    user_email: str,
) -> bool:
    """Send REPLY via msmtp."""
    user_name = resolve_user_name(user_email)

    # Create email message
    msg = MIMEMultipart("mixed")

    # Map status to human-readable response
    status_map = {
        "ACCEPTED": "Accepted",
        "DECLINED": "Declined",
        "TENTATIVE": "Tentative",
    }
    human_status = status_map.get(status, status)

    msg["Subject"] = f"Re: {event_summary} - {human_status}"
    msg["From"] = f"{user_name} <{user_email}>"
    msg["To"] = organizer_email
    msg["Date"] = email.utils.formatdate(localtime=True)

    # Body
    body = MIMEText(
        f"This is an automatic reply to your meeting invitation.\n\nStatus: {human_status}\n",
    )
    msg.attach(body)

    # Calendar attachment
    cal_part = MIMEText(reply_cal.to_ical().decode(), "calendar")
    cal_part.add_header("Content-Disposition", 'attachment; filename="reply.ics"')
    cal_part.set_param("method", "REPLY")
    msg.attach(cal_part)

    # Send via msmtp
    try:
        result = subprocess.run(
            ["msmtp", "-t"],
            input=msg.as_string(),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as e:
        msg_str = f"Failed to run msmtp: {e}"
        raise SendError(msg_str) from e
    if result.returncode != 0:
        msg_str = f"msmtp failed: {result.stderr.strip()}"
        raise SendError(msg_str)
    return True


def _set_attendee_partstat(cal: Calendar, user_email: str, ical_status: str) -> bool:
    """Set PARTSTAT for *user_email* in all VEVENTs of *cal*. Returns True if changed."""
    changed = False
    lower_email = user_email.lower()
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        for att in get_attendee_list(component):
            att_email = strip_mailto(str(att)).lower()
            if att_email == lower_email:
                att.params["PARTSTAT"] = ical_status
                changed = True
    return changed


def _update_local_partstat(
    original_cal: Calendar,
    user_email: str,
    ical_status: str,
    calendars_dir: str | None = None,
) -> None:
    """Update our PARTSTAT in the locally stored .ics file.

    After sending a REPLY, the local copy should reflect our new
    status (ACCEPTED/DECLINED/TENTATIVE) so that `calendar-cli list -v`
    shows the correct value.
    """
    # Lazy import to avoid circular dependency (import_invite → reply)
    from .import_invite import _find_existing_ics  # noqa: PLC0415
    from .store import _resolve_calendars_dir, atomic_write  # noqa: PLC0415

    resolved_dir = str(_resolve_calendars_dir(calendars_dir))

    for component in original_cal.walk():
        if component.name != "VEVENT":
            continue
        uid = str(component.get("uid", ""))
        if not uid:
            continue

        existing = _find_existing_ics(uid, resolved_dir)
        if existing is None:
            continue

        try:
            cal = Calendar.from_ical(existing.read_bytes())
        except (ValueError, OSError):
            continue

        if _set_attendee_partstat(cal, user_email, ical_status):
            atomic_write(existing, cal.to_ical())
        break


def read_email_content(file_path: str | None) -> str:
    """Read email content from file or stdin.

    Raises ``InvalidInputError`` if the file doesn't exist.
    """
    if file_path:
        p = Path(file_path)
        if not p.exists():
            msg = f"File not found: {file_path}"
            raise InvalidInputError(msg)
        try:
            with p.open(encoding="utf-8", errors="surrogateescape") as f:
                return f.read()
        except OSError as e:
            msg = f"Failed to read {file_path}: {e}"
            raise InvalidInputError(msg) from e
    return sys.stdin.read()


def extract_event_info(original_cal: Calendar) -> tuple[str | None, str]:
    """Extract organizer email and event summary from calendar."""
    organizer_email = None
    event_summary = "Meeting"

    for component in original_cal.walk():
        if component.name == "VEVENT":
            if "organizer" in component:
                organizer_email = strip_mailto(str(component["organizer"]))
            if "summary" in component:
                event_summary = str(component["summary"])
            break

    return organizer_email, event_summary


def run(config: ReplyConfig) -> int:
    """Run the reply command with the given configuration."""
    # Map user-friendly status to iCalendar format
    status_map = {
        "accept": "ACCEPTED",
        "decline": "DECLINED",
        "tentative": "TENTATIVE",
    }
    ical_status = status_map[config.status]

    # Read input
    email_content = read_email_content(config.file_path)

    # Extract calendar from email
    original_cal, user_email = extract_calendar_from_email(email_content)
    if not original_cal:
        msg = "No calendar invite found in input"
        raise ParseError(msg)

    if not user_email:
        msg = "No recipient email found in input"
        raise ParseError(msg)

    # Find organizer email and event summary
    organizer_email, event_summary = extract_event_info(original_cal)

    if not organizer_email:
        msg = "No organizer found in calendar invite"
        raise ParseError(msg)

    # Create reply
    reply_cal = create_reply(original_cal, ical_status, user_email, config.comment)

    if config.dry_run:
        print(f"Would send reply to: {organizer_email}")
        print(f"Status: {ical_status}")
        print("\nReply calendar:")
        print(reply_cal.to_ical().decode())
    else:
        send_reply(reply_cal, organizer_email, event_summary, ical_status, user_email)
        print(f"Successfully sent {config.status} reply to {organizer_email}")
        # Update our PARTSTAT in the local calendar store
        _update_local_partstat(
            original_cal, user_email, ical_status, config.calendars_dir
        )

    return 0


def _handle_args(args: argparse.Namespace) -> int:
    """Handle parsed arguments and run the command."""
    config = ReplyConfig(
        status=args.status,
        file_path=args.file,
        comment=args.comment,
        dry_run=args.dry_run,
        calendars_dir=getattr(args, "calendar_dir", None),
    )
    return run(config)


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the reply subcommand."""
    parser = subparsers.add_parser(
        "reply",
        help="Reply to calendar invites with RSVP responses",
        description="Send RSVP responses (accept/decline/tentative) to calendar invitations",
    )

    parser.add_argument(
        "status",
        choices=["accept", "decline", "tentative"],
        help="RSVP response status",
    )
    parser.add_argument(
        "-c",
        "--comment",
        help="Optional comment to include with response",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Print the reply instead of sending",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Email file containing invite (reads from stdin if not provided)",
    )

    parser.set_defaults(func=_handle_args)
