"""Date/time helpers for sanitizing and coercing calendar values."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar.timezone.windows_to_olson import WINDOWS_TO_OLSON

from .errors import InvalidInputError

log = logging.getLogger(__name__)


def localize_naive(naive: datetime, tz: ZoneInfo) -> datetime:
    """Attach a timezone to a naive datetime, handling DST transitions.

    - Gap (spring-forward): uses the post-transition offset (fold=1).
    - Ambiguous (fall-back): uses the first occurrence (fold=0).
    """
    dt0 = naive.replace(tzinfo=tz, fold=0)
    dt1 = naive.replace(tzinfo=tz, fold=1)
    off0 = dt0.utcoffset()
    off1 = dt1.utcoffset()
    if off0 != off1 and off0 is not None and off1 is not None and off0 < off1:
        return dt1
    return dt0


def parse_datetime(s: str, tz_name: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM' in the given Olson timezone.

    Raises ``InvalidInputError`` for unparseable input or unknown timezones.
    Handles DST transitions correctly via ``localize_naive``.
    """
    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, ZoneInfoNotFoundError):
        msg = f"Unknown timezone: {tz_name}"
        raise InvalidInputError(msg) from None
    try:
        normalized = s.replace("T", " ")
        naive = datetime.strptime(normalized, "%Y-%m-%d %H:%M")  # noqa: DTZ007
    except ValueError:
        msg = f"Invalid date/time format: {s!r} (expected YYYY-MM-DD HH:MM)"
        raise InvalidInputError(msg) from None
    return localize_naive(naive, tz)


def normalize_windows_tzid(tzid: str) -> str:
    """Convert Windows timezone names to Olson (e.g. 'Eastern Standard Time' → 'America/New_York').

    Outlook sends Windows-style TZIDs that most Unix tools don't
    understand.  Returns the input unchanged if it's already Olson.
    """
    result: str = WINDOWS_TO_OLSON.get(tzid, tzid)
    return result


def default_duration(dtstart: datetime | date) -> timedelta:
    return timedelta(hours=1) if isinstance(dtstart, datetime) else timedelta(days=1)


def _fix_mismatched_tz(dtstart: datetime, dtend: datetime) -> tuple[datetime, datetime]:
    if dtstart.tzinfo and not dtend.tzinfo:
        log.warning("DTEND has no timezone, copying from DTSTART")
        dtend = dtend.replace(tzinfo=dtstart.tzinfo)
    elif not dtstart.tzinfo and dtend.tzinfo:
        log.warning("DTSTART has no timezone, copying from DTEND")
        dtstart = dtstart.replace(tzinfo=dtend.tzinfo)
    return dtstart, dtend


def coerce_to_datetime(dt: datetime | date) -> datetime:
    """Promote a bare ``date`` to a midnight UTC ``datetime``.

    Needed so that mixed date/datetime pairs can be compared without
    raising ``TypeError``.  Already-datetime values pass through unchanged.
    """
    if isinstance(dt, datetime):
        return dt
    return datetime.combine(dt, datetime.min.time(), tzinfo=UTC)


def _coerce_mixed_types(
    dtstart: datetime | date,
    dtend: datetime | date,
) -> tuple[datetime | date, datetime | date]:
    """Coerce a date/datetime pair to a common type.

    Real-world ICS producers (Outlook, some Google Calendar exports)
    sometimes emit a DATE for DTSTART but a DATETIME for DTEND or vice
    versa.  Coerce to datetime so comparisons don't crash.
    """
    start_is_dt = isinstance(dtstart, datetime)
    end_is_dt = isinstance(dtend, datetime)
    if start_is_dt != end_is_dt:
        log.warning("DTSTART/DTEND type mismatch (date vs datetime), coercing")
        return coerce_to_datetime(dtstart), coerce_to_datetime(dtend)
    return dtstart, dtend


def sanitize_timerange(
    dtstart: datetime | date,
    dtend: datetime | date | None,
    duration: timedelta | None = None,
) -> tuple[datetime | date, datetime | date]:
    """Fix missing or broken DTEND — same heuristics as khal.

    - Missing DTEND + no DURATION → 1 hour (datetime) or 1 day (date)
    - DTEND == DTSTART → assume 1 hour / 1 day
    - Mismatched tzinfo → copy from the one that has it
    - Mixed date/datetime → coerce to datetime (prevents TypeError)
    """
    if dtend is not None:
        dtstart, dtend = _coerce_mixed_types(dtstart, dtend)

    if isinstance(dtstart, datetime) and isinstance(dtend, datetime):
        dtstart, dtend = _fix_mismatched_tz(dtstart, dtend)

    if dtend is None:
        effective_duration = duration or default_duration(dtstart)
        if effective_duration.total_seconds() < 0:
            log.warning("Negative DURATION, using absolute value")
            effective_duration = abs(effective_duration)
        dtend = dtstart + effective_duration
    elif dtend < dtstart:
        log.warning("DTEND < DTSTART, swapping")
        dtstart, dtend = dtend, dtstart
    elif dtend == dtstart:
        log.debug("DTEND == DTSTART, assuming 1 hour / 1 day")
        dtend = dtstart + default_duration(dtstart)

    return dtstart, dtend
