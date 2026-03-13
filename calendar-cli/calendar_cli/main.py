"""calendar-cli — manage local vdirsyncer calendars from the command line."""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

from . import create, import_invite, reply, store
from .errors import (
    CalendarCliError,
    EventNotFoundError,
    InvalidInputError,
)
from .timeutil import parse_datetime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today() -> date:
    return datetime.now(tz=UTC).date()


def _parse_date(s: str) -> date:
    """Parse YYYY-MM-DD or relative like 'today', '+7d'.

    Raises ``InvalidInputError`` for malformed input.
    """
    low = s.lower().strip()
    today = _today()
    if low == "today":
        return today
    if low == "tomorrow":
        return today + timedelta(days=1)
    if low.startswith("+") and low.endswith("d"):
        try:
            return today + timedelta(days=int(low[1:-1]))
        except ValueError:
            msg = f"Invalid relative date: {s!r} (expected e.g. +7d)"
            raise InvalidInputError(msg) from None
    try:
        return date.fromisoformat(s)
    except ValueError:
        msg = f"Invalid date: {s!r} (expected YYYY-MM-DD, today, tomorrow, or +Nd)"
        raise InvalidInputError(msg) from None


def _detect_local_tz() -> tzinfo:
    """Detect the system's local timezone as a ZoneInfo object.

    Falls back to a fixed UTC offset if detection fails.  Uses a proper
    ZoneInfo so DST transitions are handled correctly (e.g. CET ↔ CEST).
    """
    tz_env = os.environ.get("TZ")
    if tz_env:
        with contextlib.suppress(KeyError):
            return ZoneInfo(tz_env)

    localtime = Path("/etc/localtime")
    if localtime.is_symlink():
        parts = str(localtime.resolve()).split("/zoneinfo/")
        if len(parts) == 2:
            with contextlib.suppress(KeyError):
                return ZoneInfo(parts[1])

    tz_file = Path("/etc/timezone")
    if tz_file.exists():
        with contextlib.suppress(KeyError, OSError):
            return ZoneInfo(tz_file.read_text().strip())

    # Last resort: fixed offset from system clock
    now = datetime.now(tz=UTC).astimezone()
    assert now.tzinfo is not None  # guaranteed by astimezone()
    return now.tzinfo


_LOCAL_TZ = _detect_local_tz()


def _format_dt(dt: datetime | date) -> str:
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(_LOCAL_TZ)
        return dt.strftime("%a %Y-%m-%d %H:%M")
    return dt.strftime("%a %Y-%m-%d")


def _format_end(dtstart: datetime | date, dtend: datetime | date | None) -> str:
    """Format the end time, omitting the date when it matches the start."""
    if dtend is None:
        return ""
    if isinstance(dtstart, datetime) and isinstance(dtend, datetime):
        start_local = dtstart.astimezone(_LOCAL_TZ) if dtstart.tzinfo else dtstart
        end_local = dtend.astimezone(_LOCAL_TZ) if dtend.tzinfo else dtend
        if start_local.date() == end_local.date():
            return end_local.strftime("%H:%M")
    return _format_dt(dtend)


# Statuses that are the default / uninteresting — suppress from display
_QUIET_STATUSES = {"", "CONFIRMED"}


_vdirsyncer_available: bool | None = None


def _sync() -> None:
    """Run vdirsyncer sync (silently).  Skips if vdirsyncer is not on PATH."""
    global _vdirsyncer_available  # noqa: PLW0603
    if _vdirsyncer_available is None:
        _vdirsyncer_available = shutil.which("vdirsyncer") is not None
    if not _vdirsyncer_available:
        return
    result = subprocess.run(
        ["vdirsyncer", "sync"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        print(f"Warning: vdirsyncer sync failed: {stderr}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Color support (only when stdout is a TTY)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ

# ANSI escape helpers — return empty strings when color is disabled.
_RESET = "\033[0m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_DIM = "\033[2m" if _USE_COLOR else ""
_CYAN = "\033[36m" if _USE_COLOR else ""
_GREEN = "\033[32m" if _USE_COLOR else ""
_YELLOW = "\033[33m" if _USE_COLOR else ""
_RED = "\033[31m" if _USE_COLOR else ""
_MAGENTA = "\033[35m" if _USE_COLOR else ""
_BLUE = "\033[34m" if _USE_COLOR else ""


_MAX_DESCRIPTION_LEN = 200


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to *max_len* chars, appending '…' if shortened."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _format_time_range(ev: store.CalendarEvent) -> str:
    """Format the start-end time range for display."""
    start = _format_dt(ev.dtstart)
    end = _format_end(ev.dtstart, ev.dtend)
    if end:
        return f"{start} \N{EN DASH} {end}"
    return start


def _ev_date(ev: store.CalendarEvent) -> date:
    """Return the local date for an event's start."""
    dt = ev.dtstart
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(_LOCAL_TZ)
        return dt.date()
    return dt


def _status_color(status: str) -> str:
    """Return an ANSI color for the given status."""
    if status == "TENTATIVE":
        return _YELLOW
    if status == "CANCELLED":
        return _RED
    return ""


def _print_event(
    ev: store.CalendarEvent,
    *,
    verbose: bool = False,
    full: bool = False,
) -> None:
    time_range = _format_time_range(ev)
    sc = _status_color(ev.status)
    status = f" {sc}[{ev.status}]{_RESET}" if ev.status not in _QUIET_STATUSES else ""
    print(
        f"{_CYAN}{time_range}{_RESET}  "
        f"{_BOLD}{ev.summary}{_RESET}{status} "
        f"{_DIM}| {ev.calendar} [{ev.uid}]{_RESET}"
    )
    if verbose or full:
        _print_detail(ev, full=full)


_LABEL_WIDTH = 13  # "Description: " is the widest label


def _print_field(label: str, value: str, color: str = _GREEN) -> None:
    """Print a labeled detail field with consistent indentation.

    Multi-line values are indented to align with the first line's content.
    """
    pad = " " * _LABEL_WIDTH
    prefix = f"  {color}{label + ':':<{_LABEL_WIDTH}}{_RESET}"
    lines = value.splitlines()
    print(f"{prefix}{lines[0]}")
    for line in lines[1:]:
        print(f"  {pad}{line}")


def _print_detail(ev: store.CalendarEvent, *, full: bool = False) -> None:
    """Print verbose/full detail fields for an event."""
    if ev.location:
        _print_field("Location", ev.location)
    if ev.url:
        _print_field("URL", ev.url)
    if ev.organizer:
        _print_field("Organizer", ev.organizer)
    if ev.attendees:
        _print_field("Attendees", ", ".join(str(a) for a in ev.attendees))
    if ev.description:
        desc = (
            ev.description if full else _truncate(ev.description, _MAX_DESCRIPTION_LEN)
        )
        _print_field("Description", desc)
    if ev.rrule:
        _print_field("Recurrence", ev.rrule, color=_MAGENTA)
    if ev.alarms:
        _print_field("Alarms", ", ".join(ev.alarms), color=_YELLOW)


def _print_event_list(
    events: list[store.CalendarEvent],
    *,
    verbose: bool = False,
) -> None:
    """Print events with blank-line separators between different days."""
    prev_date: date | None = None
    for ev in events:
        ev_date = _ev_date(ev)
        if prev_date is not None and ev_date != prev_date:
            print()
        prev_date = ev_date
        _print_event(ev, verbose=verbose)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_calendars(args: argparse.Namespace) -> int:
    names = store.discover_calendars(args.calendar_dir)
    if not names:
        print("No calendars found.", file=sys.stderr)
        return 1
    for n in names:
        print(n)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from_date = _parse_date(args.from_date) if args.from_date else _today()
    to_date = (
        _parse_date(args.to_date)
        if args.to_date
        else from_date + timedelta(days=args.days)
    )

    if args.sync:
        _sync()

    events = store.list_events(
        calendars_dir=args.calendar_dir,
        calendar_filter=args.calendar,
        from_date=from_date,
        to_date=to_date,
    )

    if not events:
        print("No events found.")
        return 0

    limit = args.limit
    shown = events[:limit] if limit else events
    _print_event_list(shown, verbose=args.verbose)

    remaining = len(events) - len(shown)
    if remaining > 0:
        print(f"\n... {remaining} more event(s) not shown (use --limit to increase)")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    if args.sync:
        _sync()
    ev = store.get_event(args.uid, args.calendar_dir)
    if ev is None:
        msg = f"Event not found: {args.uid}"
        raise EventNotFoundError(msg)
    _print_event(ev, full=True)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    if args.sync:
        _sync()

    events = store.search_events(
        query=args.query,
        calendars_dir=args.calendar_dir,
        calendar_filter=args.calendar,
    )

    if not events:
        print("No matching events found.")
        return 0

    limit = args.limit
    shown = events[:limit] if limit else events
    _print_event_list(shown, verbose=args.verbose)

    remaining = len(events) - len(shown)
    if remaining > 0:
        print(f"\n... {remaining} more event(s) not shown (use --limit to increase)")

    return 0


def _parse_date_only(s: str) -> date:
    """Parse 'YYYY-MM-DD' into a date object."""
    return datetime.strptime(s, "%Y-%m-%d").date()  # noqa: DTZ007


def _parse_all_day_times(
    args: argparse.Namespace,
) -> tuple[date, date]:
    """Parse start/end for --all-day events.

    Per RFC 5545, DTEND for DATE values is exclusive and must be
    strictly after DTSTART.  If end == start we treat it as a
    single-day event (bump to start + 1 day).  If end < start
    we reject it.
    """
    try:
        dtstart = _parse_date_only(args.start.replace("T", " ").split(" ")[0])
    except ValueError:
        msg = f"Invalid start date: {args.start!r}"
        raise InvalidInputError(msg) from None
    if args.end:
        try:
            dtend = _parse_date_only(args.end.replace("T", " ").split(" ")[0])
        except ValueError:
            msg = f"Invalid end date: {args.end!r}"
            raise InvalidInputError(msg) from None
        if dtend < dtstart:
            msg = f"End date ({dtend}) is before start date ({dtstart})"
            raise InvalidInputError(msg)
        if dtend == dtstart:
            # Single-day event — DTEND is exclusive per RFC 5545
            dtend = dtstart + timedelta(days=1)
    else:
        dtend = dtstart + timedelta(days=args.days or 1)
    return dtstart, dtend


def _parse_timed_times(
    args: argparse.Namespace,
) -> tuple[datetime, datetime]:
    """Parse start/end for timed events."""
    if not args.timezone:
        msg = "--timezone is required (unless --all-day)"
        raise InvalidInputError(msg)
    tz_name = args.timezone
    dtstart = parse_datetime(args.start, tz_name)
    if args.end:
        dtend = parse_datetime(args.end, tz_name)
    else:
        dtend = dtstart + timedelta(minutes=args.duration)
    return dtstart, dtend


def _parse_new_times(
    args: argparse.Namespace,
) -> tuple[datetime | date, datetime | date]:
    """Parse start/end from 'new' args."""
    return _parse_all_day_times(args) if args.all_day else _parse_timed_times(args)


def cmd_new(args: argparse.Namespace) -> int:
    dtstart, dtend = _parse_new_times(args)

    alarm_minutes = _parse_alarms(args.alarm) if args.alarm else None

    ev = store.create_event(
        summary=args.summary,
        dtstart=dtstart,
        dtend=dtend,
        calendar_name=args.calendar,
        calendars_dir=args.calendar_dir,
        location=args.location or "",
        description=args.description or "",
        rrule=args.rrule or "",
        alarm_minutes=alarm_minutes,
    )

    _sync()

    print(f"Created: {ev.uid}")
    _print_event(ev)
    return 0


def _parse_edit_times(args: argparse.Namespace, kwargs: dict[str, object]) -> None:
    """Parse --start/--end into kwargs."""
    if args.start is None and args.end is None:
        return
    if not args.timezone:
        msg = "--timezone is required when changing --start or --end"
        raise InvalidInputError(msg)
    for flag, key in [("start", "dtstart"), ("end", "dtend")]:
        value = getattr(args, flag)
        if value is not None:
            kwargs[key] = parse_datetime(value, args.timezone)


def _collect_edit_kwargs(args: argparse.Namespace) -> dict[str, object]:
    """Extract edit fields from args."""
    kwargs: dict[str, object] = {}
    if args.summary is not None:
        kwargs["summary"] = args.summary
    _parse_edit_times(args, kwargs)
    if args.location is not None:
        kwargs["location"] = args.location
    if args.description is not None:
        kwargs["description"] = args.description
    if args.rrule is not None:
        kwargs["rrule"] = args.rrule
    if args.alarm is not None:
        kwargs["alarm_minutes"] = _parse_alarms(args.alarm)
    return kwargs


def cmd_edit(args: argparse.Namespace) -> int:
    kwargs = _collect_edit_kwargs(args)

    ev = store.update_event(args.uid, args.calendar_dir, **kwargs)  # type: ignore[arg-type]
    if ev is None:
        msg = f"Event not found: {args.uid}"
        raise EventNotFoundError(msg)

    _sync()

    print(f"Updated: {ev.uid}")
    _print_event(ev)
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    if not store.delete_event(args.uid, args.calendar_dir):
        msg = f"Event not found: {args.uid}"
        raise EventNotFoundError(msg)

    _sync()

    print(f"Deleted: {args.uid}")
    return 0


# ---------------------------------------------------------------------------
# Alarm helper
# ---------------------------------------------------------------------------


def _parse_alarms(raw: list[str]) -> list[int]:
    """Parse alarm specs like '15m', '1h', '1d' into minutes.

    Raises ``InvalidInputError`` for malformed specs.
    """
    multipliers = {"m": 1, "h": 60, "d": 60 * 24}
    result: list[int] = []
    for raw_spec in raw:
        spec = raw_spec.strip().lower()
        if not spec:
            msg = f"Invalid alarm spec: {raw_spec!r} (expected e.g. 15m, 1h, 1d, or bare minutes)"
            raise InvalidInputError(msg)
        if spec[-1] in multipliers:
            digits = spec[:-1]
            multiplier = multipliers[spec[-1]]
        else:
            digits = spec
            multiplier = 1
        try:
            result.append(int(digits) * multiplier)
        except ValueError:
            msg = f"Invalid alarm spec: {raw_spec!r} (expected e.g. 15m, 1h, 1d, or bare minutes)"
            raise InvalidInputError(msg) from None
    return result


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="calendar-cli",
        description="Manage local vdirsyncer calendars",
    )
    parser.add_argument(
        "--calendar-dir",
        default=None,
        help=f"Calendar root dir (default: {store.DEFAULT_CALENDARS_DIR} or $CALENDAR_DIR)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run vdirsyncer sync before the command",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- calendars ---
    sub.add_parser("calendars", help="List available calendars")

    # --- list ---
    p_list = sub.add_parser(
        "list",
        help="List events",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  calendar-cli list                        # today + 7 days
  calendar-cli list --from today --days 30
  calendar-cli list --calendar personal
  calendar-cli list --from 2025-04-01 --to 2025-04-07
""",
    )
    p_list.add_argument("-c", "--calendar", help="Filter by calendar name")
    p_list.add_argument(
        "--from",
        dest="from_date",
        default="today",
        help="Start date: YYYY-MM-DD, 'today', 'tomorrow', '+Nd' (default: today)",
    )
    p_list.add_argument(
        "--to",
        dest="to_date",
        help="End date (exclusive). Overrides --days.",
    )
    p_list.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to show (default: 7)",
    )
    p_list.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show location, description, rrule",
    )
    p_list.add_argument(
        "-n",
        "--limit",
        type=int,
        default=50,
        help="Max events to show (default: 50, 0 = unlimited)",
    )

    # --- show ---
    p_show = sub.add_parser("show", help="Show a single event by UID")
    p_show.add_argument("uid", help="Event UID")

    # --- search ---
    p_search = sub.add_parser(
        "search",
        help="Search events by regex",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  calendar-cli search dentist
  calendar-cli search "team.*meeting" -v
  calendar-cli search "sprint|retro" -c work
""",
    )
    p_search.add_argument(
        "query", help="Regex to match against summary, location, description"
    )
    p_search.add_argument("-c", "--calendar", help="Filter by calendar name")
    p_search.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show location, description, rrule",
    )
    p_search.add_argument(
        "-n",
        "--limit",
        type=int,
        default=20,
        help="Max results to show (default: 20, 0 = unlimited)",
    )

    # --- new ---
    p_new = sub.add_parser(
        "new",
        help="Create a new event",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  calendar-cli new "Team Meeting" --start 2025-04-01T14:00 --timezone Europe/Berlin -d 60 -c personal
  calendar-cli new "Dinner" --start "2025-04-01 19:00" --end "2025-04-01 21:00" \\
      --location "Restaurant" --timezone Europe/Berlin
  calendar-cli new "Day Off" --start 2025-04-01 --all-day
  calendar-cli new "Vacation" --start 2025-04-01 --end 2025-04-05 --all-day
  calendar-cli new "Standup" --start 2025-04-01T09:00 --timezone America/New_York -d 15 \\
      --rrule "FREQ=WEEKLY;BYDAY=MO,WE,FR" --alarm 15m
""",
    )
    p_new.add_argument("summary", help="Event title")
    p_new.add_argument(
        "--start",
        required=True,
        help="Start: 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM' (date only for --all-day)",
    )
    p_new.add_argument(
        "--end",
        help="End: 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM' (date only for --all-day)",
    )
    p_new.add_argument(
        "-d",
        "--duration",
        type=int,
        default=60,
        help="Duration in minutes (default: 60, ignored for --all-day)",
    )
    p_new.add_argument(
        "--all-day",
        action="store_true",
        help="Create an all-day event (DTSTART/DTEND are dates, not datetimes)",
    )
    p_new.add_argument(
        "--days",
        type=int,
        help="Duration in days for --all-day events (default: 1)",
    )
    p_new.add_argument(
        "-c",
        "--calendar",
        default="personal",
        help="Calendar name (default: personal)",
    )
    p_new.add_argument("-l", "--location", help="Location")
    p_new.add_argument("--description", help="Description text")
    p_new.add_argument(
        "--timezone",
        help="Olson timezone, e.g. Europe/Berlin, America/New_York (required unless --all-day)",
    )
    p_new.add_argument(
        "--rrule",
        help="iCalendar RRULE, e.g. 'FREQ=WEEKLY;COUNT=10'",
    )
    p_new.add_argument(
        "--alarm",
        action="append",
        help="Alarm before event: '15m', '1h', '1d' (repeatable)",
    )

    # --- edit ---
    p_edit = sub.add_parser(
        "edit",
        help="Edit an existing event",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  calendar-cli edit <uid> --summary "New Title"
  calendar-cli edit <uid> --start "2025-04-02 10:00" --end "2025-04-02 11:00"
  calendar-cli edit <uid> --location "Room 42"
""",
    )
    p_edit.add_argument("uid", help="Event UID")
    p_edit.add_argument("--summary", help="New title")
    p_edit.add_argument("--start", help="New start time: 'YYYY-MM-DD HH:MM'")
    p_edit.add_argument("--end", help="New end time: 'YYYY-MM-DD HH:MM'")
    p_edit.add_argument("-l", "--location", help="New location")
    p_edit.add_argument("--description", help="New description")
    p_edit.add_argument(
        "--timezone",
        help="Olson timezone, e.g. Europe/Berlin (required when changing times)",
    )
    p_edit.add_argument("--rrule", help="New RRULE (empty string to clear)")
    p_edit.add_argument(
        "--alarm",
        action="append",
        help="New alarm(s): '15m', '1h', '1d' (replaces all)",
    )

    # --- delete ---
    p_delete = sub.add_parser("delete", help="Delete an event by UID")
    p_delete.add_argument("uid", help="Event UID")

    # --- vcal subcommands (create invite, import, reply) ---
    create.register_parser(sub)
    import_invite.register_parser(sub)
    reply.register_parser(sub)

    return parser


def _global_flag_parser() -> argparse.ArgumentParser:
    """Parser that only knows global flags, used to extract them from remaining args."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--calendar-dir", default=None)
    p.add_argument("--sync", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Use parse_known_args so global flags (--sync, --calendar-dir)
    # are accepted both before and after the subcommand.
    args, remaining = parser.parse_known_args(argv)
    if remaining:
        gp = _global_flag_parser()
        extra, unknown = gp.parse_known_args(remaining)
        if unknown:
            # Truly unknown flags — re-parse strictly for the error message.
            parser.parse_args(argv)
        if extra.calendar_dir is not None:
            args.calendar_dir = extra.calendar_dir
        if extra.sync:
            args.sync = True

    dispatch = {
        "calendars": cmd_calendars,
        "list": cmd_list,
        "show": cmd_show,
        "search": cmd_search,
        "new": cmd_new,
        "edit": cmd_edit,
        "delete": cmd_delete,
    }

    # vcal subcommands (create, import, reply) use args.func
    handler = dispatch.get(args.command) or getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except CalendarCliError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
