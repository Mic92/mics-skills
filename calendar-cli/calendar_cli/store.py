"""Read/write vdirsyncer filesystem calendar stores.

vdirsyncer stores one .ics file per event in a directory per calendar:
  ~/.local/share/calendars/<calendar>/<uid>.ics

This module provides a thin layer over the icalendar library to
list, read, create, update and delete events without depending on khal.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import tempfile
import uuid
from datetime import UTC, date, datetime, timedelta
from hashlib import sha1
from pathlib import Path

from dateutil.rrule import rrule, rruleset, rrulestr
from icalendar import Alarm, Calendar, Component, Event

from .errors import CalendarNotFoundError, InvalidInputError
from .models import CalendarEvent
from .parse import read_event_file
from .timeutil import (
    coerce_to_datetime,
    default_duration,
)
from .util import add_vtimezones, new_calendar, parse_rrule_string

__all__ = [
    "DEFAULT_CALENDARS_DIR",
    "CalendarEvent",
    "atomic_write",
    "create_event",
    "delete_event",
    "discover_calendars",
    "generate_uid",
    "get_event",
    "list_events",
    "search_events",
    "uid_to_filename",
    "update_event",
]

log = logging.getLogger(__name__)

DEFAULT_CALENDARS_DIR = "~/.local/share/calendars"

# Characters safe for use in filenames — matches khal/vdirsyncer convention.
_SAFE_UID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-+@"
)


def uid_to_filename(uid: str) -> str:
    """Convert a UID to a safe filename, hashing if it contains unsafe chars.

    vdirsyncer expects filenames to be safe for the filesystem and to
    match the UID where possible.  If the UID contains characters outside
    the safe set (e.g. slashes, spaces, colons), we hash it with SHA-1
    instead — the same strategy khal uses.
    """
    if uid and not (set(uid) - _SAFE_UID_CHARS):
        return uid
    return sha1(uid.encode(), usedforsecurity=False).hexdigest()


def atomic_write(dest: Path, data: bytes) -> None:
    """Write *data* to *dest* atomically via rename.

    Uses a temporary file in the same directory so the rename is
    guaranteed to be on the same filesystem.  This prevents vdirsyncer
    from picking up a half-written .ics file.
    """
    fd, tmp = tempfile.mkstemp(prefix=dest.name, dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).rename(dest)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp).unlink()
        raise


def generate_uid() -> str:
    """Generate a UID for events that lack one."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Calendar discovery
# ---------------------------------------------------------------------------


def _resolve_calendars_dir(calendars_dir: str | None) -> Path:
    if calendars_dir is not None:
        return Path(calendars_dir).expanduser()
    return Path(os.environ.get("CALENDAR_DIR", DEFAULT_CALENDARS_DIR)).expanduser()


def _resolve_calendar_name(base: Path, name: str) -> str:
    """Resolve a calendar name case-insensitively against existing directories.

    Returns the actual directory name if found, or the input unchanged
    (for new calendars that don't exist yet).
    """
    if (base / name).is_dir():
        return name
    lower = name.lower()
    for entry in base.iterdir():
        if entry.is_dir() and entry.name.lower() == lower:
            return entry.name
    return name


def discover_calendars(calendars_dir: str | None = None) -> list[str]:
    """Return sorted list of calendar names (subdirectories containing .ics)."""
    base = _resolve_calendars_dir(calendars_dir)
    if not base.is_dir():
        return []
    names: list[str] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        if any(entry.glob("*.ics")):
            names.append(entry.name)
        # Also check one level deeper (e.g. clan/personal)
        names.extend(
            f"{entry.name}/{sub.name}"
            for sub in sorted(entry.iterdir())
            if sub.is_dir() and any(sub.glob("*.ics"))
        )
    return sorted(set(names))


# ---------------------------------------------------------------------------
# Recurrence expansion
# ---------------------------------------------------------------------------


def _to_naive(dt: datetime | date) -> datetime:
    """Convert to a naive datetime for dateutil.rrule compatibility.

    dateutil.rrule.between() requires naive datetimes when the rule
    itself was created with a naive dtstart.  We strip tzinfo for the
    comparison and re-attach it afterwards.
    """
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=None)
    return datetime.combine(dt, datetime.min.time())


def _strip_until_tz(rrule_str: str) -> str:
    """Strip the trailing Z from UNTIL values in an RRULE string.

    dateutil requires UNTIL and DTSTART to have matching tz-awareness.
    Since we pass a naive DTSTART to rrulestr(), we must also strip the
    UTC indicator from UNTIL to avoid a ValueError.
    """
    return re.sub(r"(UNTIL=\d{8}T\d{6})Z", r"\1", rrule_str)


def _make_rrule_set(ev: CalendarEvent) -> rruleset:
    """Build a dateutil rruleset from an event's RRULE + EXDATE + RDATE."""
    rset = rruleset()

    dtstart = ev.dtstart
    naive_start = _to_naive(dtstart)

    parsed = rrulestr(_strip_until_tz(ev.rrule), dtstart=naive_start)
    if not isinstance(parsed, rrule):
        msg = f"Expected single rrule, got {type(parsed).__name__}"
        raise TypeError(msg)
    rset.rrule(parsed)

    for exdt in ev.exdates:
        rset.exdate(_to_naive(exdt))

    for rdt in ev.rdates:
        rset.rdate(_to_naive(rdt))

    return rset


def _expand_recurring(
    ev: CalendarEvent,
    from_dt: datetime,
    to_dt: datetime,
    override_dts: frozenset[datetime],
) -> list[CalendarEvent]:
    """Expand a recurring event into individual occurrences within [from_dt, to_dt).

    *override_dts* contains naive datetimes of RECURRENCE-ID overrides
    for this UID — those occurrences are suppressed since they're
    replaced by the override VEVENT.  Matching is by exact datetime
    (not just date) per RFC 5545 §3.8.4.4.
    """
    rset = _make_rrule_set(ev)

    # dateutil works with naive datetimes when dtstart is naive
    naive_from = _to_naive(from_dt)
    naive_to = _to_naive(to_dt)

    occurrences = rset.between(naive_from, naive_to, inc=True)

    # Compute event duration to derive dtend for each occurrence
    if ev.dtend is not None:
        duration = coerce_to_datetime(ev.dtend) - coerce_to_datetime(ev.dtstart)
    else:
        duration = default_duration(ev.dtstart)

    # Recover the original timezone (if any)
    orig_tz = ev.dtstart.tzinfo if isinstance(ev.dtstart, datetime) else None

    expanded: list[CalendarEvent] = []
    for occ_naive in occurrences:
        # Filter: to_dt is exclusive
        if occ_naive >= naive_to:
            continue

        # Suppress occurrences overridden by RECURRENCE-ID
        if occ_naive in override_dts:
            continue

        # Reconstruct the occurrence with original type (date or datetime)
        if ev.is_all_day:
            occ_start: datetime | date = occ_naive.date()
            occ_end: datetime | date = occ_start + duration
        else:
            occ_dt = occ_naive.replace(tzinfo=orig_tz) if orig_tz else occ_naive
            occ_start = occ_dt
            occ_end = occ_dt + duration

        expanded.append(
            CalendarEvent(
                uid=ev.uid,
                summary=ev.summary,
                dtstart=occ_start,
                dtend=occ_end,
                location=ev.location,
                description=ev.description,
                calendar=ev.calendar,
                rrule=ev.rrule,
                filepath=ev.filepath,
                alarm_minutes=ev.alarm_minutes,
                url=ev.url,
                organizer=ev.organizer,
                attendees=ev.attendees,
                status=ev.status,
            )
        )
    return expanded


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _ev_date(ev: CalendarEvent) -> date:
    return ev.dtstart.date() if isinstance(ev.dtstart, datetime) else ev.dtstart


def _ev_end_date(ev: CalendarEvent) -> date:
    """Return the last date an event occupies.

    For timed events (datetime DTEND), the event occupies the DTEND
    date if it has any time > 00:00 on that day.  For all-day events
    (date DTEND), DTEND is already exclusive per RFC 5545, so the last
    occupied date is DTEND - 1 day.  We return the exclusive end date
    (one past the last occupied day) for overlap calculations.
    """
    if ev.dtend is None:
        # No end → single-point event, exclusive end = start + 1 day
        return _ev_date(ev) + timedelta(days=1)
    if isinstance(ev.dtend, datetime):
        # A timed event ending at midnight exactly doesn't occupy that day
        if ev.dtend.hour == 0 and ev.dtend.minute == 0 and ev.dtend.second == 0:
            return ev.dtend.date()
        # Otherwise it occupies the end date; exclusive end = date + 1
        return ev.dtend.date() + timedelta(days=1)
    # All-day DTEND is already exclusive per RFC 5545
    return ev.dtend


def _in_date_range(
    ev: CalendarEvent,
    from_date: date | None,
    to_date: date | None,
) -> bool:
    """Return True if an event overlaps [from_date, to_date).

    Uses overlap logic (event_start < exclusive_end AND event_exclusive_end > from_date)
    so that multi-day events appear when querying any day they span.
    Both from_date and to_date are treated as dates (day granularity).
    """
    ev_start = _ev_date(ev)
    ev_exclusive_end = _ev_end_date(ev)
    if from_date and ev_exclusive_end <= from_date:
        return False
    return not (to_date and ev_start >= to_date)


def _collect_raw_events(
    calendars_dir: str | None,
    calendar_filter: str | None,
) -> list[CalendarEvent]:
    """Read all .ics files and return parsed CalendarEvents."""
    base = _resolve_calendars_dir(calendars_dir)
    if not base.is_dir():
        return []

    all_cals = discover_calendars(calendars_dir)
    if calendar_filter:
        resolved = _resolve_calendar_name(base, calendar_filter)
        cal_names = [resolved] if resolved in all_cals else [calendar_filter]
    else:
        cal_names = all_cals

    events: list[CalendarEvent] = []
    for cal_name in cal_names:
        cal_dir = base / cal_name
        if not cal_dir.is_dir():
            continue
        for ics_file in cal_dir.glob("*.ics"):
            events.extend(read_event_file(ics_file, cal_name))
    return events


def _split_masters_overrides(
    raw_events: list[CalendarEvent],
) -> tuple[list[CalendarEvent], dict[str, list[CalendarEvent]]]:
    """Separate master/standalone events from RECURRENCE-ID overrides."""
    overrides: dict[str, list[CalendarEvent]] = {}
    masters: list[CalendarEvent] = []
    for ev in raw_events:
        if ev.recurrence_id is not None:
            overrides.setdefault(ev.uid, []).append(ev)
        else:
            masters.append(ev)
    return masters, overrides


def _override_datetimes(
    overrides: dict[str, list[CalendarEvent]],
) -> dict[str, frozenset[datetime]]:
    """Build a mapping of UID → set of naive datetimes suppressed by RECURRENCE-ID overrides.

    Uses the exact RECURRENCE-ID value (not just the date) so that
    multiple occurrences on the same day are handled correctly per
    RFC 5545 §3.8.4.4.  Values are converted to naive datetimes to
    match the naive occurrence datetimes produced by dateutil.rrule.
    """
    result: dict[str, frozenset[datetime]] = {}
    for uid, ovrs in overrides.items():
        dts: set[datetime] = set()
        for ov in ovrs:
            if ov.recurrence_id is not None:
                dts.add(_to_naive(ov.recurrence_id))
        result[uid] = frozenset(dts)
    return result


# ---------------------------------------------------------------------------
# Public API — list / get / create / update / delete
# ---------------------------------------------------------------------------


def list_events(
    calendars_dir: str | None = None,
    calendar_filter: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[CalendarEvent]:
    """List events from the local store, optionally filtered.

    Recurring events (those with an RRULE) are expanded into individual
    occurrences within the requested date range, matching khal behaviour.
    EXDATE exclusions and RECURRENCE-ID overrides are respected.
    """
    raw_events = _collect_raw_events(calendars_dir, calendar_filter)
    masters, overrides = _split_masters_overrides(raw_events)
    override_dts_by_uid = _override_datetimes(overrides)

    events: list[CalendarEvent] = []

    # Process master / standalone events
    for ev in masters:
        if ev.rrule and from_date is not None and to_date is not None:
            from_dt = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
            to_dt = datetime.combine(to_date, datetime.min.time(), tzinfo=UTC)
            suppressed = override_dts_by_uid.get(ev.uid, frozenset())
            events.extend(_expand_recurring(ev, from_dt, to_dt, suppressed))
        elif _in_date_range(ev, from_date, to_date):
            events.append(ev)

    # Add override events (they have their own DTSTART)
    for ovr_list in overrides.values():
        events.extend(ov for ov in ovr_list if _in_date_range(ov, from_date, to_date))

    events.sort(key=lambda e: e.start_dt())
    return events


def search_events(
    query: str,
    calendars_dir: str | None = None,
    calendar_filter: str | None = None,
) -> list[CalendarEvent]:
    """Search events by regex against summary, location, and description.

    *query* is a Python regex matched case-insensitively.  Plain text
    works as-is since regex treats literal characters as themselves.

    Returns master/standalone events (no recurrence expansion) whose
    summary, location, or description matches.  Results are sorted by
    start time.

    Raises ``InvalidInputError`` for invalid regex patterns.
    """
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error as e:
        msg = f"Invalid search pattern: {e}"
        raise InvalidInputError(msg) from e
    raw_events = _collect_raw_events(calendars_dir, calendar_filter)

    # De-duplicate by UID so recurring masters appear only once
    seen_uids: set[str] = set()
    matches: list[CalendarEvent] = []
    for ev in raw_events:
        if ev.recurrence_id is not None:
            continue  # skip overrides — master is enough
        if ev.uid in seen_uids:
            continue
        if (
            pattern.search(ev.summary)
            or pattern.search(ev.location)
            or pattern.search(ev.description)
        ):
            matches.append(ev)
            seen_uids.add(ev.uid)

    matches.sort(key=lambda e: e.start_dt())
    return matches


def get_event(
    uid: str,
    calendars_dir: str | None = None,
) -> CalendarEvent | None:
    """Find a single event by UID."""
    base = _resolve_calendars_dir(calendars_dir)
    if not base.is_dir():
        return None
    for cal_name in discover_calendars(calendars_dir):
        cal_dir = base / cal_name
        for ics_file in cal_dir.glob("*.ics"):
            for ev in read_event_file(ics_file, cal_name):
                if ev.uid == uid:
                    return ev
    return None


def _build_ics(  # noqa: PLR0913
    uid: str,
    summary: str,
    dtstart: datetime | date,
    dtend: datetime | date,
    *,
    location: str = "",
    description: str = "",
    rrule: str = "",
    alarm_minutes: list[int] | None = None,
    sequence: int = 0,
) -> bytes:
    """Build a minimal VCALENDAR with one VEVENT."""
    cal = new_calendar()

    now = datetime.now(tz=UTC)

    event = Event()
    event.add("uid", uid)
    event.add("summary", summary)
    event.add("dtstart", dtstart)
    event.add("dtend", dtend)
    event.add("dtstamp", now)
    event.add("created", now)
    event.add("last-modified", now)
    event.add("sequence", sequence)
    if location:
        event.add("location", location)
    if description:
        event.add("description", description)
    if rrule:
        event.add("rrule", parse_rrule_string(rrule))

    for minutes in alarm_minutes or []:
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", f"Reminder: {summary}")
        alarm.add("trigger", timedelta(minutes=-minutes))
        event.add_component(alarm)

    add_vtimezones(cal, dtstart, dtend)
    cal.add_component(event)
    result: bytes = cal.to_ical()
    return result


def create_event(  # noqa: PLR0913
    summary: str,
    dtstart: datetime | date,
    dtend: datetime | date,
    calendar_name: str = "personal",
    calendars_dir: str | None = None,
    *,
    location: str = "",
    description: str = "",
    rrule: str = "",
    alarm_minutes: list[int] | None = None,
) -> CalendarEvent:
    """Create a new event in the local store.

    Raises CalendarNotFoundError if the calendar directory doesn't exist
    (to avoid silently creating calendars that vdirsyncer won't sync).
    """
    base = _resolve_calendars_dir(calendars_dir)
    calendar_name = _resolve_calendar_name(base, calendar_name)
    cal_dir = base / calendar_name
    if not cal_dir.is_dir():
        available = discover_calendars(calendars_dir)
        msg = f"Calendar {calendar_name!r} does not exist."
        if available:
            msg += f" Available: {', '.join(available)}"
        raise CalendarNotFoundError(msg)

    uid = generate_uid()
    ics_data = _build_ics(
        uid,
        summary,
        dtstart,
        dtend,
        location=location,
        description=description,
        rrule=rrule,
        alarm_minutes=alarm_minutes,
    )

    filepath = cal_dir / f"{uid_to_filename(uid)}.ics"
    atomic_write(filepath, ics_data)

    return CalendarEvent(
        uid=uid,
        summary=summary,
        dtstart=dtstart,
        dtend=dtend,
        location=location,
        description=description,
        calendar=calendar_name,
        rrule=rrule,
        filepath=filepath,
        alarm_minutes=alarm_minutes or [],
    )


def delete_event(
    uid: str,
    calendars_dir: str | None = None,
) -> bool:
    """Delete an event by UID. Returns True if found and deleted."""
    ev = get_event(uid, calendars_dir)
    if ev is None:
        return False
    try:
        ev.filepath.unlink()
    except OSError as e:
        msg = f"Failed to delete {ev.filepath}: {e}"
        raise CalendarNotFoundError(msg) from e
    return True


def _patch_vevent(  # noqa: PLR0913, C901
    filepath: Path,
    uid: str,
    *,
    summary: str | None = None,
    dtstart: datetime | date | None = None,
    dtend: datetime | date | None = None,
    location: str | None = None,
    description: str | None = None,
    rrule: str | None = None,
    alarm_minutes: list[int] | None = None,
) -> bytes:
    """Patch a VEVENT in-place, preserving all unmodified properties.

    Reads the existing .ics file, modifies only the requested fields in
    the matching VEVENT, increments SEQUENCE, updates LAST-MODIFIED and
    DTSTAMP, and returns the serialized VCALENDAR bytes.

    This preserves ORGANIZER, ATTENDEE, STATUS, URL, CATEGORIES, CLASS,
    GEO, RECURRENCE-ID, X-* properties, and VTIMEZONE components that
    would be lost by a full rebuild.
    """
    try:
        data = filepath.read_text()
    except OSError as e:
        msg = f"Failed to read {filepath}: {e}"
        raise CalendarNotFoundError(msg) from e
    cal = Calendar.from_ical(data)

    now = datetime.now(tz=UTC)

    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        if str(component.get("uid", "")) != uid:
            continue

        # Patch simple text properties
        _patch_prop(component, "summary", summary)
        _patch_prop(component, "location", location)
        _patch_prop(component, "description", description)

        # Patch time properties
        if dtstart is not None:
            _patch_prop(component, "dtstart", dtstart)
        if dtend is not None:
            _patch_prop(component, "dtend", dtend)

        # Patch RRULE
        if rrule is not None:
            if "rrule" in component:
                del component["rrule"]
            if rrule:
                component.add("rrule", parse_rrule_string(rrule))

        # Patch alarms — replace all VALARM subcomponents
        if alarm_minutes is not None:
            component.subcomponents = [
                sc for sc in component.subcomponents if sc.name != "VALARM"
            ]
            event_summary = str(component.get("summary", "Event"))
            for minutes in alarm_minutes:
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", f"Reminder: {event_summary}")
                alarm.add("trigger", timedelta(minutes=-minutes))
                component.add_component(alarm)

        # Increment SEQUENCE (RFC 5545 §3.8.7.4)
        old_seq = int(component.get("sequence", 0))
        _patch_prop(component, "sequence", old_seq + 1)

        # Update timestamps
        _patch_prop(component, "last-modified", now)
        _patch_prop(component, "dtstamp", now)

        break

    result: bytes = cal.to_ical()
    return result


def _patch_prop(component: Component, name: str, value: object) -> None:
    """Set a property on a VEVENT, replacing any existing value."""
    if value is None:
        return
    if name in component:
        del component[name]
    component.add(name, value)


def update_event(  # noqa: PLR0913
    uid: str,
    calendars_dir: str | None = None,
    *,
    summary: str | None = None,
    dtstart: datetime | date | None = None,
    dtend: datetime | date | None = None,
    location: str | None = None,
    description: str | None = None,
    rrule: str | None = None,
    alarm_minutes: list[int] | None = None,
) -> CalendarEvent | None:
    """Update an existing event. Only provided fields are changed.

    Patches the existing .ics file in-place so that unmodified
    properties (ORGANIZER, ATTENDEE, STATUS, URL, X-* etc.) are
    preserved.  Increments SEQUENCE per RFC 5545 §3.8.7.4.
    """
    ev = get_event(uid, calendars_dir)
    if ev is None:
        return None

    ics_data = _patch_vevent(
        ev.filepath,
        uid,
        summary=summary,
        dtstart=dtstart,
        dtend=dtend,
        location=location,
        description=description,
        rrule=rrule,
        alarm_minutes=alarm_minutes,
    )

    atomic_write(ev.filepath, ics_data)

    # Re-read the patched event to return accurate data
    return get_event(uid, calendars_dir)
