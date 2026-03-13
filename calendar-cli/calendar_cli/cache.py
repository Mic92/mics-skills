"""SQLite cache for parsed calendar events.

Avoids re-parsing every .ics file on each invocation.  The cache stores
pre-parsed VEVENT fields and uses file mtime+size for invalidation:
only changed/new files are re-parsed, and removed files are purged.

Cache location: ``$XDG_CACHE_HOME/calendar-cli/cache.db``
(defaults to ``~/.cache/calendar-cli/cache.db``).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Attendee, CalendarEvent
from .parse import read_event_file

__all__ = ["cached_collect_events"]

log = logging.getLogger(__name__)

_SCHEMA_VERSION = 3

_CREATE_SQL = """\
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    path  TEXT    PRIMARY KEY,
    mtime REAL    NOT NULL,
    size  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    path          TEXT    NOT NULL REFERENCES files(path),
    calendar      TEXT    NOT NULL,
    uid           TEXT    NOT NULL,
    summary       TEXT    NOT NULL DEFAULT '',
    dtstart       TEXT    NOT NULL,
    dtend         TEXT,
    is_all_day    INTEGER NOT NULL DEFAULT 0,
    location      TEXT    NOT NULL DEFAULT '',
    description   TEXT    NOT NULL DEFAULT '',
    rrule         TEXT    NOT NULL DEFAULT '',
    url           TEXT    NOT NULL DEFAULT '',
    organizer     TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT '',
    recurrence_id TEXT,
    alarm_minutes TEXT    NOT NULL DEFAULT '[]',
    attendees     TEXT    NOT NULL DEFAULT '[]',
    exdates       TEXT    NOT NULL DEFAULT '[]',
    rdates        TEXT    NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_events_path ON events(path);
CREATE INDEX IF NOT EXISTS idx_events_uid ON events(uid);
CREATE INDEX IF NOT EXISTS idx_events_calendar ON events(calendar);
"""


# ---------------------------------------------------------------------------
# Date/time serialization
# ---------------------------------------------------------------------------


def _dt_to_str(dt: datetime | date) -> str:
    """Serialize a date or datetime to a string for storage.

    For timezone-aware datetimes with an Olson timezone (ZoneInfo), the
    timezone key is appended in brackets so it survives a round-trip:
    ``2026-02-23T10:00:00-05:00[America/New_York]``.

    This is critical for recurring events that cross DST boundaries:
    ``fromisoformat()`` would otherwise convert ZoneInfo to a fixed UTC
    offset, causing all occurrences to use the DTSTART offset regardless
    of whether DST is active.
    """
    if isinstance(dt, datetime):
        iso = dt.isoformat()
        if isinstance(dt.tzinfo, ZoneInfo):
            iso += f"[{dt.tzinfo.key}]"
        return iso
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime | date:
    """Deserialize a date or datetime from storage.

    ISO 8601 date strings (YYYY-MM-DD, 10 chars) → ``date``.
    Strings with a bracketed Olson zone suffix (e.g. ``[America/New_York]``)
    restore the proper ``ZoneInfo`` so DST transitions work correctly.
    Everything else → ``datetime.fromisoformat()``.
    """
    if len(s) == 10:
        return date.fromisoformat(s)
    # Check for bracketed Olson timezone suffix
    if s.endswith("]"):
        bracket = s.rfind("[")
        if bracket != -1:
            tz_key = s[bracket + 1 : -1]
            iso_part = s[:bracket]
            dt = datetime.fromisoformat(iso_part)
            return dt.replace(tzinfo=ZoneInfo(tz_key))
    return datetime.fromisoformat(s)


# ---------------------------------------------------------------------------
# Row ↔ CalendarEvent conversion
# ---------------------------------------------------------------------------


def _event_to_row(ev: CalendarEvent) -> tuple[object, ...]:
    """Convert a CalendarEvent to a database row tuple."""
    return (
        str(ev.filepath),
        ev.calendar,
        ev.uid,
        ev.summary,
        _dt_to_str(ev.dtstart),
        _dt_to_str(ev.dtend) if ev.dtend is not None else None,
        1 if ev.is_all_day else 0,
        ev.location,
        ev.description,
        ev.rrule,
        ev.url,
        ev.organizer,
        ev.status,
        _dt_to_str(ev.recurrence_id) if ev.recurrence_id is not None else None,
        json.dumps(ev.alarm_minutes),
        json.dumps(
            [
                {"email": a.email, "name": a.name, "status": a.status}
                for a in ev.attendees
            ]
        ),
        json.dumps([_dt_to_str(d) for d in ev.exdates]),
        json.dumps([_dt_to_str(d) for d in ev.rdates]),
    )


def _row_to_event(row: sqlite3.Row) -> CalendarEvent:
    """Convert a database row to a CalendarEvent."""
    attendees_raw = json.loads(row["attendees"])
    attendees = [
        Attendee(email=a["email"], name=a["name"], status=a["status"])
        for a in attendees_raw
    ]
    exdates = [_str_to_dt(s) for s in json.loads(row["exdates"])]
    rdates = [_str_to_dt(s) for s in json.loads(row["rdates"])]
    rec_id = (
        _str_to_dt(row["recurrence_id"]) if row["recurrence_id"] is not None else None
    )
    dtend = _str_to_dt(row["dtend"]) if row["dtend"] is not None else None

    return CalendarEvent(
        uid=row["uid"],
        summary=row["summary"],
        dtstart=_str_to_dt(row["dtstart"]),
        dtend=dtend,
        location=row["location"],
        description=row["description"],
        calendar=row["calendar"],
        rrule=row["rrule"],
        filepath=Path(row["path"]),
        alarm_minutes=json.loads(row["alarm_minutes"]),
        url=row["url"],
        organizer=row["organizer"],
        attendees=attendees,
        status=row["status"],
        recurrence_id=rec_id,
        exdates=exdates,
        rdates=rdates,
    )


# ---------------------------------------------------------------------------
# Cache database management
# ---------------------------------------------------------------------------


def _cache_db_path() -> Path:
    """Return the cache database path, respecting XDG_CACHE_HOME."""
    cache_home = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache_home) / "calendar-cli" / "cache.db"


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the cache database, handling schema migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Check schema version
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        version = int(row["value"]) if row else 0
    except sqlite3.OperationalError:
        version = 0

    if version != _SCHEMA_VERSION:
        # Drop and recreate on version mismatch
        conn.executescript(
            "DROP TABLE IF EXISTS events;"
            "DROP TABLE IF EXISTS files;"
            "DROP TABLE IF EXISTS meta;"
        )
        conn.executescript(_CREATE_SQL)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(_SCHEMA_VERSION),),
        )
        conn.commit()

    return conn


def _stat_file(path: Path) -> tuple[float, int]:
    """Return (mtime, size) for a file."""
    st = path.stat()
    return (st.st_mtime, st.st_size)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def cached_collect_events(
    ics_files: list[tuple[Path, str]],
    *,
    db_path: Path | None = None,
) -> list[CalendarEvent]:
    """Load events using the cache, re-parsing only changed files.

    *ics_files* is a list of ``(path, calendar_name)`` tuples — the
    caller discovers which files to load, and this function handles
    caching.

    Returns all CalendarEvent objects from those files.
    """
    if db_path is None:
        db_path = _cache_db_path()

    try:
        conn = _open_db(db_path)
    except (OSError, sqlite3.Error) as exc:
        log.debug("Cache unavailable (%s), falling back to direct parse", exc)
        return _parse_all(ics_files)

    try:
        return _sync_and_query(conn, ics_files)
    except (OSError, sqlite3.DatabaseError) as exc:
        log.debug("Cache error (%s), falling back to direct parse", exc)
        return _parse_all(ics_files)
    finally:
        conn.close()


def _parse_all(ics_files: list[tuple[Path, str]]) -> list[CalendarEvent]:
    """Parse all .ics files without caching (fallback for read-only environments)."""
    events: list[CalendarEvent] = []
    for path, cal_name in ics_files:
        events.extend(read_event_file(path, cal_name))
    return events


def _stat_ics_files(
    ics_files: list[tuple[Path, str]],
) -> dict[str, tuple[float, int, str]]:
    """Stat all .ics files and return ``{path: (mtime, size, calendar)}``."""
    current: dict[str, tuple[float, int, str]] = {}
    for path, cal_name in ics_files:
        try:
            mtime, size = _stat_file(path)
            current[str(path)] = (mtime, size, cal_name)
        except OSError:
            continue  # file disappeared between discovery and stat
    return current


def _find_changes(
    current_files: dict[str, tuple[float, int, str]],
    conn: sqlite3.Connection,
) -> tuple[set[str], set[str], set[str]]:
    """Compare filesystem state against cache, return (new, stale, removed) paths."""
    cached: dict[str, tuple[float, int]] = {}
    for row in conn.execute("SELECT path, mtime, size FROM files"):
        cached[row["path"]] = (row["mtime"], row["size"])

    current_paths = set(current_files.keys())
    cached_paths = set(cached.keys())

    removed = cached_paths - current_paths
    new = current_paths - cached_paths
    stale: set[str] = set()
    for path_str in current_paths & cached_paths:
        cur_mtime, cur_size, _ = current_files[path_str]
        old_mtime, old_size = cached[path_str]
        if cur_mtime != old_mtime or cur_size != old_size:
            stale.add(path_str)

    return new, stale, removed


_INSERT_EVENT_SQL = """
    INSERT INTO events (
        path, calendar, uid, summary, dtstart, dtend,
        is_all_day, location, description, rrule, url, organizer,
        status, recurrence_id, alarm_minutes, attendees, exdates, rdates
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _apply_changes(
    conn: sqlite3.Connection,
    current_files: dict[str, tuple[float, int, str]],
    new: set[str],
    stale: set[str],
    removed: set[str],
) -> None:
    """Delete outdated rows and insert re-parsed events."""
    to_delete = removed | stale
    if to_delete:
        conn.executemany("DELETE FROM events WHERE path = ?", [(p,) for p in to_delete])
        conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in to_delete])

    to_reparse = stale | new
    if to_reparse:
        file_rows: list[tuple[str, float, int]] = []
        event_rows: list[tuple[object, ...]] = []
        for path_str in to_reparse:
            mtime, size, cal_name = current_files[path_str]
            file_rows.append((path_str, mtime, size))
            event_rows.extend(
                _event_to_row(ev) for ev in read_event_file(Path(path_str), cal_name)
            )
        conn.executemany(
            "INSERT INTO files (path, mtime, size) VALUES (?, ?, ?)", file_rows
        )
        conn.executemany(_INSERT_EVENT_SQL, event_rows)

    if to_delete or to_reparse:
        conn.commit()
        log.debug(
            "Cache sync: %d new, %d stale, %d removed",
            len(new),
            len(stale),
            len(removed),
        )


def _query_events(
    conn: sqlite3.Connection,
    paths: set[str],
) -> list[CalendarEvent]:
    """Read cached events for the given file paths."""
    if not paths:
        return []

    events: list[CalendarEvent] = []
    path_list = list(paths)
    batch_size = 500
    for i in range(0, len(path_list), batch_size):
        batch = path_list[i : i + batch_size]
        placeholders = ",".join("?" * len(batch))
        sql = f"SELECT * FROM events WHERE path IN ({placeholders})"  # noqa: S608
        events.extend(_row_to_event(row) for row in conn.execute(sql, batch))

    return events


def _sync_and_query(
    conn: sqlite3.Connection,
    ics_files: list[tuple[Path, str]],
) -> list[CalendarEvent]:
    """Sync the cache with the filesystem, then return all events."""
    current_files = _stat_ics_files(ics_files)
    new, stale, removed = _find_changes(current_files, conn)
    _apply_changes(conn, current_files, new, stale, removed)
    return _query_events(conn, set(current_files.keys()))
