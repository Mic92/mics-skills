#!/usr/bin/env python3
"""Generate ICS calendar invites and send them via msmtp.

Supports attendees with names/emails and meeting links.
"""

from __future__ import annotations

import argparse
import email.utils
import os
import pwd
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Alarm, Calendar, Event, vCalAddress, vText

from .config import load_config_or_exit
from .email_invite import EmailConfig, build_invite_email, send_invite_email
from .errors import InvalidInputError
from .store import atomic_write
from .timeutil import parse_datetime
from .util import add_vtimezones, new_calendar, parse_rrule_string


@dataclass
class MeetingConfig:
    """Configuration for a meeting invitation."""

    summary: str
    start: datetime
    end: datetime
    organizer_name: str
    organizer_email: str
    attendees: list[tuple[str, str]]
    location: str | None = None
    meeting_link: str | None = None
    description: str | None = None
    reminder_minutes: int = 15
    tz: str = "UTC"
    recurrence: dict[str, object] | None = None


@dataclass
class CreateConfig:
    """Configuration for create command."""

    meeting: MeetingConfig
    output_ics: str | None = None
    output_email: str | None = None
    dry_run: bool = False
    calendar_dir: str = "~/.local/share/calendars/personal"
    no_local_save: bool = False


def validate_email(email: str) -> None:
    """Validate email has proper format with username@domain.tld."""
    if "@" not in email:
        msg = f"Invalid email address (missing @): {email}"
        raise InvalidInputError(msg)

    # Split and validate parts
    parts = email.split("@")
    expected_parts = 2
    if len(parts) != expected_parts or not parts[0] or not parts[1]:
        msg = f"Invalid email address format: {email}"
        raise InvalidInputError(msg)

    # Basic domain validation - must have at least one dot
    if "." not in parts[1]:
        msg = f"Invalid email domain (missing dot): {email}"
        raise InvalidInputError(msg)


def parse_attendees(attendees_str: str) -> list[tuple[str, str]]:
    """Parse attendee string format: 'Name <email>' or just 'email'."""
    attendees: list[tuple[str, str]] = []
    # Handle empty string
    if not attendees_str.strip():
        return attendees

    for attendee_str in attendees_str.split(","):
        attendee = attendee_str.strip()
        if not attendee:  # Skip empty items from split
            continue

        # Use email.utils.parseaddr to parse the email
        parsed_name, parsed_email = email.utils.parseaddr(attendee)

        # parseaddr returns ('', '') for completely invalid input
        if not parsed_email:
            msg = f"Invalid email address: {attendee}"
            raise InvalidInputError(msg)

        # Validate email format
        validate_email(parsed_email)

        attendees.append((parsed_name, parsed_email))

    return attendees


def _build_invite_description(config: MeetingConfig) -> str | None:
    """Build event description with optional meeting link."""
    parts = []
    if config.description:
        parts.append(config.description)
    if config.meeting_link:
        parts.append(f"\nJoin meeting: {config.meeting_link}")
    return "\n".join(parts) if parts else None


def _build_invite_event(config: MeetingConfig) -> Event:
    """Build the VEVENT component for a calendar invite."""
    now = datetime.now(UTC)
    event = Event()

    event.add("summary", config.summary)
    event.add("dtstart", config.start)
    event.add("dtend", config.end)
    event.add("dtstamp", now)
    event.add("created", now)
    event.add("uid", f"{uuid.uuid4()}@calendar-invite-generator")
    event.add("sequence", 0)
    event.add("status", "CONFIRMED")
    event.add("transp", "OPAQUE")

    if config.location:
        event.add("location", config.location)

    desc = _build_invite_description(config)
    if desc:
        event.add("description", desc)

    # Organizer
    organizer = vCalAddress(f"mailto:{config.organizer_email}")
    organizer.params["cn"] = vText(config.organizer_name)
    event.add("organizer", organizer)

    # Organizer as attendee (so it appears in their calendar)
    org_attendee = vCalAddress(f"mailto:{config.organizer_email}")
    org_attendee.params["cn"] = vText(config.organizer_name)
    org_attendee.params["partstat"] = vText("ACCEPTED")
    org_attendee.params["role"] = vText("REQ-PARTICIPANT")
    event.add("attendee", org_attendee)

    # Invited attendees
    for name, email_addr in config.attendees:
        attendee = vCalAddress(f"mailto:{email_addr}")
        if name:
            attendee.params["cn"] = vText(name)
        attendee.params["partstat"] = vText("NEEDS-ACTION")
        attendee.params["rsvp"] = vText("TRUE")
        attendee.params["role"] = vText("REQ-PARTICIPANT")
        event.add("attendee", attendee)

    # Reminder alarm
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", f"Reminder: {config.summary}")
    alarm.add("trigger", timedelta(minutes=-config.reminder_minutes))
    event.add_component(alarm)

    if config.recurrence:
        event.add("rrule", config.recurrence)

    return event


def create_calendar_invite(config: MeetingConfig) -> Calendar:
    """Create an ICS calendar invite."""
    cal = new_calendar(method="REQUEST")
    add_vtimezones(cal, config.start, config.end)
    cal.add_component(_build_invite_event(config))
    return cal


def get_organizer_info(args: argparse.Namespace) -> tuple[str, str]:
    """Get organizer name and email from args or system."""
    # Load config once (will exit on error)
    config = load_config_or_exit()

    # Try to get name from args, then config, then system
    organizer_name = args.organizer_name
    if not organizer_name and config.user:
        organizer_name = config.user.name

    if not organizer_name:
        try:
            # Try to get the real name from passwd entry
            pw_entry = pwd.getpwuid(os.getuid())
            organizer_name = pw_entry.pw_gecos.split(",")[0]
            # Fallback to username if gecos is empty
            if not organizer_name:
                organizer_name = pw_entry.pw_name
        except (KeyError, OSError):
            # Last resort fallback
            organizer_name = "Meeting Organizer"

    # Try to get email from args, then config
    organizer_email = args.organizer_email
    if not organizer_email and config.user:
        organizer_email = config.user.email

    return organizer_name, organizer_email


def parse_meeting_time(
    args: argparse.Namespace,
    tz: ZoneInfo,
) -> tuple[datetime, datetime]:
    """Parse start time and calculate end time."""
    if args.start:
        start = parse_datetime(args.start, str(tz))
    else:
        # Default to next hour
        now = datetime.now(tz)
        start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    end = start + timedelta(minutes=args.duration)
    return start, end


def parse_recurrence_options(
    args: argparse.Namespace,
    tz: ZoneInfo,
) -> dict[str, Any] | None:
    """Parse recurrence options from command line arguments."""
    if args.rrule:
        return parse_rrule_string(args.rrule)

    if not args.repeat:
        return None

    # Build recurrence rule from simple options
    rrule: dict[str, Any] = {}

    # Set frequency
    freq_map = {
        "daily": "DAILY",
        "weekly": "WEEKLY",
        "biweekly": "WEEKLY",
        "monthly": "MONTHLY",
        "yearly": "YEARLY",
    }
    rrule["FREQ"] = freq_map[args.repeat]

    # Handle biweekly
    if args.repeat == "biweekly":
        rrule["INTERVAL"] = 2

    # Handle weekdays for weekly recurrence
    if args.repeat in ["weekly", "biweekly"] and args.weekdays:
        # Split comma-separated weekdays into a list
        rrule["BYDAY"] = [day.strip().upper() for day in args.weekdays.split(",")]

    # Handle count or until
    if args.count:
        rrule["COUNT"] = args.count
    elif args.until:
        try:
            until_date = datetime.strptime(args.until, "%Y-%m-%d")  # noqa: DTZ007
            # Convert to UTC for iCalendar - use datetime object directly
            until_dt = until_date.replace(hour=23, minute=59, second=59).replace(
                tzinfo=tz
            )
            rrule["UNTIL"] = until_dt.astimezone(UTC)
        except ValueError:
            msg = "Invalid until date format. Use YYYY-MM-DD"
            raise InvalidInputError(msg) from None

    return rrule


def save_ics_file(cal: Calendar, output: str | None, start: datetime) -> None:
    """Save ICS file if requested."""
    if output:
        output_file = output
    else:
        # Generate filename from summary and date
        event = cal.walk("vevent")[0]
        summary = str(event.get("summary", "meeting"))
        safe_summary = re.sub(r"[^\w\s-]", "", summary).strip().replace(" ", "-")
        date_str = start.strftime("%Y%m%d")
        output_file = f"{safe_summary}-{date_str}.ics"

    output_path = Path(output_file)
    try:
        with output_path.open("wb") as f:
            f.write(cal.to_ical())
    except OSError as e:
        msg = f"Failed to write {output_path}: {e}"
        raise InvalidInputError(msg) from e


def save_to_local_calendar(cal: Calendar, calendar_dir: str) -> None:
    """Save event to local calendar directory (atomically)."""
    cal_dir = Path(calendar_dir).expanduser()
    if cal_dir.is_dir():
        # Generate unique filename using UID
        event_uid = cal.walk("vevent")[0]["UID"]
        calendar_file = cal_dir / f"{event_uid}.ics"
        try:
            atomic_write(calendar_file, cal.to_ical())
        except OSError as e:
            print(
                f"Warning: failed to save to local calendar: {e}",
                file=sys.stderr,
            )


def format_recurrence_description(recurrence: dict[str, object]) -> str:
    """Format recurrence rule into human-readable description."""
    recur_desc = []
    freq = str(recurrence.get("FREQ", "")).lower()
    if freq:
        interval = recurrence.get("INTERVAL", 1)
        biweekly_interval = 2
        if interval == biweekly_interval and freq == "weekly":
            recur_desc.append("Repeats: biweekly")
        else:
            recur_desc.append(f"Repeats: {freq}")

    if "BYDAY" in recurrence:
        days = recurrence["BYDAY"]
        if isinstance(days, list):
            recur_desc.append(f"on {','.join(days)}")
        else:
            recur_desc.append(f"on {days}")

    if "COUNT" in recurrence:
        recur_desc.append(f"for {recurrence['COUNT']} occurrences")
    elif "UNTIL" in recurrence:
        until = recurrence["UNTIL"]
        if isinstance(until, datetime):
            recur_desc.append(f"until {until.strftime('%Y-%m-%d')}")

    return " ".join(recur_desc)


def print_meeting_details(config: MeetingConfig) -> None:
    """Print meeting details summary."""
    # Show recurrence info
    if config.recurrence:
        recur_desc = format_recurrence_description(config.recurrence)
        if recur_desc:
            print(f"Recurrence: {recur_desc}")

    print("\nAttendees:")
    for name, email_addr in config.attendees:
        if name:
            print(f"  - {name} <{email_addr}>")
        else:
            print(f"  - {email_addr}")

    if config.meeting_link:
        print(f"\nMeeting link: {config.meeting_link}")


def run(config: CreateConfig) -> int:
    """Run the invite command with the given configuration."""
    cal = create_calendar_invite(config.meeting)

    # Save .ics file if requested
    if config.output_ics:
        save_ics_file(cal, config.output_ics, config.meeting.start)

    # Save to local calendar if not disabled
    if not config.no_local_save:
        save_to_local_calendar(cal, config.calendar_dir)

    # Build the email
    email_config = EmailConfig(
        cal=cal,
        config=config.meeting,
        dry_run=config.dry_run,
    )
    msg = build_invite_email(email_config)

    # Export email to file or stdout
    if config.output_email:
        if config.output_email == "-":
            sys.stdout.write(msg.as_string())
        else:
            try:
                Path(config.output_email).write_text(msg.as_string())
            except OSError as e:
                err_msg = f"Failed to write {config.output_email}: {e}"
                raise InvalidInputError(err_msg) from e
        return 0

    # Print meeting details (only when sending, not exporting)
    print_meeting_details(config.meeting)

    # Send via msmtp
    if not config.dry_run:
        send_invite_email(msg)

    return 0


def _handle_args(args: argparse.Namespace) -> int:
    # Parse timezone
    try:
        tz = ZoneInfo(args.timezone)
    except ZoneInfoNotFoundError:
        msg = f"Unknown timezone: {args.timezone}"
        raise InvalidInputError(msg) from None

    # Parse time and attendees
    start, end = parse_meeting_time(args, tz)
    attendees = parse_attendees(args.attendees)

    if not attendees:
        msg = "No valid attendees specified"
        raise InvalidInputError(msg)

    # Get organizer info
    organizer_name, organizer_email = get_organizer_info(args)

    # Validate organizer email
    if not organizer_email:
        msg = (
            "Organizer email is required. "
            "Use --organizer-email or create ~/.config/vcal/config.toml with:\n"
            "[user]\n"
            'email = "your@email.com"'
        )
        raise InvalidInputError(msg)

    validate_email(organizer_email)

    # Parse recurrence options
    recurrence = parse_recurrence_options(args, tz)

    # Create meeting config
    meeting = MeetingConfig(
        summary=args.summary,
        start=start,
        end=end,
        organizer_name=organizer_name,
        organizer_email=organizer_email,
        attendees=attendees,
        location=args.location,
        meeting_link=args.meeting_link,
        description=args.description,
        reminder_minutes=args.reminder,
        tz=args.timezone,
        recurrence=recurrence,
    )

    # Create full config
    config = CreateConfig(
        meeting=meeting,
        output_ics=args.output_ics,
        output_email=args.output_email,
        dry_run=args.dry_run,
        calendar_dir=args.calendar_dir or "~/.local/share/calendars/personal",
        no_local_save=args.no_local_save,
    )

    return run(config)


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the invite subcommand."""
    parser = subparsers.add_parser(
        "invite",
        help="Create and send calendar invitations via email",
        description="Generate and send ICS calendar invites via email",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple meeting
  calendar-cli invite -s "Team Meeting" -d 60 -a "john@example.com,Jane Doe <jane@example.com>"

  # Meeting with Zoom link
  calendar-cli invite -s "Project Review" -d 90 -a "team@example.com" \\
    -l "https://zoom.us/j/123456789" --meeting-link "https://zoom.us/j/123456789"

  # Specific time and timezone
  calendar-cli invite -s "Client Call" --start "2024-01-15 14:00" -d 30 \\
    -a "Client Name <client@company.com>" --timezone "America/New_York"

  # Weekly recurring meeting for 10 weeks
  calendar-cli invite -s "Weekly Standup" -d 30 -a "team@example.com" \\
    --repeat weekly --count 10

  # Export email to file instead of sending
  calendar-cli invite -s "Meeting" -a "test@example.com" \\
    --timezone UTC --output-email invite.eml

  # Save just the .ics file
  calendar-cli invite -s "Meeting" -a "test@example.com" \\
    --timezone UTC --output-ics meeting.ics --output-email /dev/null
        """,
    )

    # Add all arguments from create_argument_parser
    parser.add_argument("-s", "--summary", required=True, help="Meeting title/summary")
    parser.add_argument(
        "--start",
        help="Start time (YYYY-MM-DD HH:MM), defaults to next hour",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=int,
        default=60,
        help="Duration in minutes (default: 60)",
    )
    parser.add_argument(
        "-a",
        "--attendees",
        required=True,
        help='Comma-separated attendees: "Name <email>" or just "email"',
    )
    parser.add_argument("--organizer-name", help="Your name (defaults to system user)")
    parser.add_argument(
        "--organizer-email",
        help="Your email (can also be set in ~/.config/vcal/config.toml)",
    )
    parser.add_argument("-l", "--location", help="Meeting location")
    parser.add_argument("--meeting-link", help="Meeting URL (Zoom, Teams, etc.)")
    parser.add_argument("--description", help="Additional meeting description")
    parser.add_argument(
        "--reminder",
        type=int,
        default=15,
        help="Reminder minutes before (default: 15)",
    )
    parser.add_argument(
        "--timezone",
        required=True,
        help="Olson timezone, e.g. Europe/Berlin, America/New_York",
    )
    parser.add_argument(
        "--output-ics",
        help="Save .ics file to path",
    )
    parser.add_argument(
        "--output-email",
        help="Write full email (.eml) to path instead of sending ('-' for stdout)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without sending",
    )

    parser.add_argument(
        "--no-local-save",
        action="store_true",
        help="Do not save to local calendar",
    )

    # Recurrence options
    recurrence_group = parser.add_argument_group("recurrence options")
    recurrence_group.add_argument(
        "--repeat",
        choices=["daily", "weekly", "biweekly", "monthly", "yearly"],
        help="Simple recurrence pattern",
    )
    recurrence_group.add_argument(
        "--count",
        type=int,
        help="Number of occurrences (e.g., --repeat weekly --count 10)",
    )
    recurrence_group.add_argument(
        "--until",
        help="End date for recurrence (YYYY-MM-DD)",
    )
    recurrence_group.add_argument(
        "--weekdays",
        help="Comma-separated weekdays for weekly recurrence (e.g., MO,WE,FR)",
    )
    recurrence_group.add_argument(
        "--rrule",
        help="Custom iCalendar RRULE string (e.g., 'FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10')",
    )

    parser.set_defaults(func=_handle_args)
