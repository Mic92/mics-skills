"""Import calendar invites from email or .ics files."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from icalendar import Calendar, Event

from .store import atomic_write, generate_uid, uid_to_filename
from .timeutil import normalize_windows_tzid
from .util import (
    extract_calendar_parts_from_email,
    get_attendee_list,
    new_calendar,
    strip_mailto,
)


@dataclass
class ImportConfig:
    """Configuration for import command."""

    file_path: str | None = None
    calendar: str = "personal"
    calendars_dir: str = "~/.local/share/calendars"


# Re-export for backward compatibility (used by tests)
extract_calendar_from_email = extract_calendar_parts_from_email


def _collect_tzids(events: list[Event]) -> set[str]:
    """Return TZID strings referenced by date properties in events."""
    tzids: set[str] = set()
    for event in events:
        for prop in ("DTSTART", "DTEND", "DUE", "RECURRENCE-ID"):
            val = event.get(prop)
            if val is not None and hasattr(val, "params"):
                tzid = val.params.get("TZID")
                if tzid:
                    tzids.add(str(tzid))
    return tzids


def _build_per_uid_calendar(
    events: list[Event],
    timezones: dict[str, object],
) -> bytes:
    """Build a VCALENDAR containing all events for one UID plus their timezones."""
    out_cal = new_calendar()

    for tzid in sorted(_collect_tzids(events)):
        if tzid in timezones:
            out_cal.add_component(timezones[tzid])

    for event in events:
        out_cal.add_component(event)

    result: bytes = out_cal.to_ical()
    return result


def _find_existing_ics(uid: str, calendars_dir: str) -> Path | None:
    """Find the .ics file for a UID across all calendars.

    First checks the expected filename (fast path), then falls back
    to parsing each .ics file with icalendar to extract the UID
    (handles line-folded UIDs and filename mismatches).
    """
    base = Path(calendars_dir).expanduser()
    if not base.is_dir():
        return None
    for cal_subdir in base.iterdir():
        if not cal_subdir.is_dir():
            continue
        # Check direct children and one level deeper
        for ics_dir in [cal_subdir, *[d for d in cal_subdir.iterdir() if d.is_dir()]]:
            candidate = ics_dir / f"{uid_to_filename(uid)}.ics"
            if candidate.exists():
                return candidate
            # Fallback: parse each file to extract UID properly
            for ics_file in ics_dir.glob("*.ics"):
                try:
                    cal = Calendar.from_ical(ics_file.read_bytes())
                    for component in cal.walk():
                        if (
                            component.name == "VEVENT"
                            and str(component.get("uid", "")) == uid
                        ):
                            return ics_file
                except (ValueError, OSError):
                    continue
    return None


def _handle_cancel(
    events_by_uid: dict[str, list[Event]],
    calendars_dir: str,
) -> int:
    """Handle METHOD:CANCEL — delete or mark matching events as CANCELLED.

    Returns the number of events processed.
    """
    count = 0
    for uid in events_by_uid:
        existing = _find_existing_ics(uid, calendars_dir)
        if existing is not None:
            try:
                existing.unlink()
            except OSError as e:
                print(f"Warning: failed to delete {existing}: {e}", file=sys.stderr)
                continue
            print(f"Cancelled event: {uid}")
            count += 1
        else:
            print(f"Warning: cancel for unknown event {uid}", file=sys.stderr)
    return count


def _extract_reply_statuses(
    reply_events: list[Event],
) -> list[tuple[str, str]]:
    """Extract (email, new_partstat) pairs from REPLY VEVENTs."""
    result: list[tuple[str, str]] = []
    for reply_ev in reply_events:
        for reply_att in get_attendee_list(reply_ev):
            email_addr = strip_mailto(str(reply_att)).lower()
            status = str(reply_att.params.get("PARTSTAT", "NEEDS-ACTION"))
            result.append((email_addr, status))
    return result


def _apply_partstat_updates(
    cal: Calendar,
    updates: list[tuple[str, str]],
    uid: str,
) -> int:
    """Apply PARTSTAT updates to attendees in a parsed calendar. Returns count."""
    count = 0
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        for att in get_attendee_list(component):
            att_email = strip_mailto(str(att)).lower()
            for reply_email, new_status in updates:
                if att_email == reply_email:
                    att.params["PARTSTAT"] = new_status
                    print(f"Updated {reply_email} → {new_status} for {uid}")
                    count += 1
    return count


def _handle_reply(
    events_by_uid: dict[str, list[Event]],
    calendars_dir: str,
) -> int:
    """Handle METHOD:REPLY — update PARTSTAT for the replying attendee.

    Returns the number of events processed.
    """
    count = 0
    for uid, reply_events in events_by_uid.items():
        existing = _find_existing_ics(uid, calendars_dir)
        if existing is None:
            print(f"Warning: reply for unknown event {uid}", file=sys.stderr)
            continue

        try:
            cal = Calendar.from_ical(existing.read_bytes())
        except (ValueError, OSError):
            continue

        updates = _extract_reply_statuses(reply_events)
        count += _apply_partstat_updates(cal, updates, uid)
        atomic_write(existing, cal.to_ical())

    return count


def _collect_components(
    cal: Calendar,
) -> tuple[dict[str, object], dict[str, list[Event]]]:
    """Collect VTIMEZONEs and group VEVENTs by UID from a parsed calendar."""
    timezones: dict[str, object] = {}
    events_by_uid: dict[str, list[Event]] = {}
    for component in cal.walk():
        if component.name == "VTIMEZONE":
            raw_tzid = component.get("TZID")
            if not raw_tzid:
                continue
            raw_tzid = str(raw_tzid)
            timezones[raw_tzid] = component
            timezones[normalize_windows_tzid(raw_tzid)] = component
        elif component.name == "VEVENT":
            uid = str(component.get("uid", ""))
            if not uid:
                uid = generate_uid()
                component.add("uid", uid)
            events_by_uid.setdefault(uid, []).append(component)
    return timezones, events_by_uid


def _ensure_calendar_dir(calendars_dir: str, calendar_name: str) -> Path | None:
    """Create the calendar directory, returning the path or None on failure."""
    cal_dir = Path(calendars_dir).expanduser() / calendar_name
    try:
        cal_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"Error: failed to create calendar directory {cal_dir}: {e}",
            file=sys.stderr,
        )
        return None
    return cal_dir


def import_to_local(
    calendar_data: bytes,
    calendar_name: str,
    calendars_dir: str = "~/.local/share/calendars",
) -> bool:
    """Import calendar data by writing .ics files to the local store.

    Inspects the METHOD property (RFC 6047) to handle different iTIP
    message types:

    - REQUEST / PUBLISH / missing: save events to the local store
    - CANCEL: delete the matching local event
    - REPLY: update attendee PARTSTAT in the existing local event

    Groups VEVENTs by UID (so recurring events with RECURRENCE-ID stay
    together), includes referenced VTIMEZONEs, and writes one .ics file
    per UID — matching khal/vdirsyncer conventions.

    Sanitization applied during import:
    - Windows timezone names converted to Olson (Outlook compatibility)
    - Events without UID get a generated one (sha256 of content)
    - Filenames with unsafe chars get SHA-1 hashed
    - Writes are atomic (tempfile + rename)
    """
    try:
        cal = Calendar.from_ical(calendar_data)
    except (ValueError, TypeError) as e:
        print(f"Error parsing calendar data: {e}", file=sys.stderr)
        return False

    # Check METHOD for iTIP dispatch (RFC 6047)
    method = str(cal.get("method", "")).upper()

    timezones, events_by_uid = _collect_components(cal)
    if not events_by_uid:
        return False

    if method == "CANCEL":
        return _handle_cancel(events_by_uid, calendars_dir) > 0

    if method == "REPLY":
        return _handle_reply(events_by_uid, calendars_dir) > 0

    # REQUEST, PUBLISH, or no method — save to local store
    cal_dir = _ensure_calendar_dir(calendars_dir, calendar_name)
    if cal_dir is None:
        return False

    for uid, events in events_by_uid.items():
        filepath = cal_dir / f"{uid_to_filename(uid)}.ics"
        atomic_write(filepath, _build_per_uid_calendar(events, timezones))

    return True


def sync_calendar() -> None:
    """Sync calendar with server using vdirsyncer."""
    try:
        result = subprocess.run(
            ["vdirsyncer", "sync"], check=False, capture_output=True
        )
    except FileNotFoundError:
        print("Warning: vdirsyncer not found, skipping sync", file=sys.stderr)
        return
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        print(f"Warning: vdirsyncer sync failed: {stderr}", file=sys.stderr)


def process_input(file_path: str | None) -> list[bytes]:
    """Process input and extract calendar data from a file or stdin."""
    calendars: list[bytes] = []

    if file_path:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: File '{file_path}' not found", file=sys.stderr)
            return []

        try:
            content = path.read_bytes()
        except OSError as e:
            print(f"Error: failed to read '{file_path}': {e}", file=sys.stderr)
            return []

        if path.suffix.lower() == ".ics":
            if b"BEGIN:VCALENDAR" in content:
                calendars.append(content)
        else:
            calendars.extend(extract_calendar_parts_from_email(content))
    else:
        content = sys.stdin.buffer.read()
        email_calendars = extract_calendar_parts_from_email(content)
        if email_calendars:
            calendars.extend(email_calendars)
        elif b"BEGIN:VCALENDAR" in content and not content.startswith(b"Content-Type:"):
            calendars.append(content)

    return calendars


def _calendar_has_rsvp(cal_data: bytes) -> bool:
    """Check if calendar data contains RSVP requests by parsing the iCalendar structure."""
    try:
        cal = Calendar.from_ical(cal_data)
    except (ValueError, TypeError):
        return False
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        for attendee in get_attendee_list(component):
            if hasattr(attendee, "params"):
                rsvp = str(attendee.params.get("RSVP", "")).upper()
                if rsvp == "TRUE":
                    return True
    return False


def import_calendars(
    calendars: list[bytes],
    calendar_name: str,
    calendars_dir: str = "~/.local/share/calendars",
) -> tuple[int, bool]:
    """Import calendar data. Returns (imported_count, has_rsvp)."""
    imported = 0
    has_rsvp = False

    for cal_data in calendars:
        if _calendar_has_rsvp(cal_data):
            has_rsvp = True

        if import_to_local(cal_data, calendar_name, calendars_dir):
            imported += 1
            print("Successfully imported calendar")
        else:
            print("Warning: Failed to import calendar", file=sys.stderr)

    return imported, has_rsvp


def run(config: ImportConfig) -> int:
    """Run the import command with the given configuration."""
    calendars = process_input(config.file_path)

    if not calendars:
        print("No .ics files found in the input", file=sys.stderr)
        return 1

    imported, has_rsvp = import_calendars(
        calendars, config.calendar, config.calendars_dir
    )

    if imported == 0:
        return 1

    sync_calendar()

    print(f"Successfully imported {imported} calendar invite(s) to {config.calendar}")

    if has_rsvp:
        print(
            "Hint: This invite requests an RSVP. "
            "Use 'calendar-cli reply accept|decline|tentative <file>' to respond."
        )

    return 0


def _handle_args(args: argparse.Namespace) -> int:
    """Handle parsed arguments and run the command."""
    from .store import _resolve_calendars_dir  # noqa: PLC0415

    calendars_dir = str(_resolve_calendars_dir(getattr(args, "calendar_dir", None)))
    config = ImportConfig(
        file_path=args.file,
        calendar=args.calendar,
        calendars_dir=calendars_dir,
    )
    return run(config)


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the import subcommand."""
    parser = subparsers.add_parser(
        "import",
        help="Import invites, process RSVP replies, and handle cancellations",
        description="Process any incoming calendar email:\n\n"
        "  - New invites        → saved to local calendar\n"
        "  - Attendee responses → updates their accept/decline status\n"
        "  - Cancellations      → removes the event locally\n\n"
        "Pipe any calendar email through this command — the action\n"
        "is detected automatically from the .ics content.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-c",
        "--calendar",
        default="personal",
        help="Calendar name (default: personal)",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="File to import (reads from stdin if not provided)",
    )

    parser.set_defaults(func=_handle_args)
