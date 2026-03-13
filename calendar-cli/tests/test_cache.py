"""Tests for the SQLite event cache."""

import os
from datetime import date
from pathlib import Path

from calendar_cli import store
from calendar_cli.cache import cached_collect_events

from .helpers import ICSEvent, make_ics, setup_single_calendar


def test_cache_returns_same_events_as_direct_parse(tmp_path: Path) -> None:
    """Cached results should match direct file parsing."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="cache-test@example.com",
                summary="Cached Event",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
                vevent_lines=["LOCATION:Room 1", "DESCRIPTION:Test"],
            )
        ),
        filename="event.ics",
    )

    db_path = tmp_path / "cache.db"
    ics_files = [(Path(cal_dir) / "personal" / "event.ics", "personal")]

    events = cached_collect_events(ics_files, db_path=db_path)
    assert len(events) == 1
    ev = events[0]
    assert ev.uid == "cache-test@example.com"
    assert ev.summary == "Cached Event"
    assert ev.location == "Room 1"
    assert ev.description == "Test"


def test_cache_second_load_uses_cache(tmp_path: Path) -> None:
    """Second call should read from cache (same results, no re-parse)."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="cached@example.com",
                summary="Persistent",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
            )
        ),
        filename="event.ics",
    )

    db_path = tmp_path / "cache.db"
    ics_files = [(Path(cal_dir) / "personal" / "event.ics", "personal")]

    events1 = cached_collect_events(ics_files, db_path=db_path)
    events2 = cached_collect_events(ics_files, db_path=db_path)
    assert len(events1) == len(events2) == 1
    assert events1[0].uid == events2[0].uid


def test_cache_invalidates_on_mtime_change(tmp_path: Path) -> None:
    """Cache should re-parse when a file's mtime changes."""
    ics_path = tmp_path / "personal" / "event.ics"
    setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="mtime@example.com",
                summary="Original",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
            )
        ),
        filename="event.ics",
    )

    db_path = tmp_path / "cache.db"
    ics_files = [(ics_path, "personal")]

    events1 = cached_collect_events(ics_files, db_path=db_path)
    assert events1[0].summary == "Original"

    # Overwrite with different content
    ics_path.write_text(
        make_ics(
            ICSEvent(
                uid="mtime@example.com",
                summary="Updated",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
            )
        )
    )

    events2 = cached_collect_events(ics_files, db_path=db_path)
    assert events2[0].summary == "Updated"


def test_cache_handles_removed_files(tmp_path: Path) -> None:
    """Cache should drop events for deleted files."""
    ics_path = tmp_path / "personal" / "event.ics"
    setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="gone@example.com",
                summary="Will be deleted",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
            )
        ),
        filename="event.ics",
    )

    db_path = tmp_path / "cache.db"
    ics_files = [(ics_path, "personal")]

    events1 = cached_collect_events(ics_files, db_path=db_path)
    assert len(events1) == 1

    # Remove the file and query with empty file list
    ics_path.unlink()
    events2 = cached_collect_events([], db_path=db_path)
    assert len(events2) == 0


def test_cache_preserves_all_fields(tmp_path: Path) -> None:
    """All CalendarEvent fields should survive the cache round-trip."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="full@example.com",
                summary="Full Event",
                dtstart=";TZID=Europe/Berlin:20250401T090000",
                dtend=";TZID=Europe/Berlin:20250401T100000",
                vevent_lines=[
                    "LOCATION:Conference Room",
                    "DESCRIPTION:Important meeting",
                    "URL:https://example.com",
                    "STATUS:CONFIRMED",
                    "ORGANIZER;CN=Boss:mailto:boss@example.com",
                    "ATTENDEE;PARTSTAT=ACCEPTED;CN=Alice:mailto:alice@example.com",
                    "RRULE:FREQ=WEEKLY;COUNT=5",
                    "EXDATE;TZID=Europe/Berlin:20250408T090000",
                    "RDATE;TZID=Europe/Berlin:20250410T090000",
                    "BEGIN:VALARM",
                    "TRIGGER:-PT15M",
                    "ACTION:DISPLAY",
                    "DESCRIPTION:Reminder",
                    "END:VALARM",
                ],
            )
        ),
        filename="full.ics",
    )

    db_path = tmp_path / "cache.db"
    ics_files = [(Path(cal_dir) / "personal" / "full.ics", "personal")]

    events = cached_collect_events(ics_files, db_path=db_path)
    assert len(events) == 1
    ev = events[0]

    assert ev.uid == "full@example.com"
    assert ev.summary == "Full Event"
    assert ev.location == "Conference Room"
    assert ev.description == "Important meeting"
    assert ev.url == "https://example.com"
    assert ev.status == "CONFIRMED"
    assert "Boss" in ev.organizer
    assert len(ev.attendees) == 1
    assert ev.attendees[0].email == "alice@example.com"
    assert ev.attendees[0].status == "ACCEPTED"
    assert "FREQ=WEEKLY" in ev.rrule
    assert len(ev.exdates) == 1
    assert len(ev.rdates) == 1
    assert ev.alarm_minutes == [15]
    assert ev.calendar == "personal"

    # Second load from cache should be identical
    events2 = cached_collect_events(ics_files, db_path=db_path)
    ev2 = events2[0]
    assert ev2.uid == ev.uid
    assert ev2.summary == ev.summary
    assert ev2.location == ev.location
    assert ev2.rrule == ev.rrule
    assert len(ev2.exdates) == len(ev.exdates)
    assert len(ev2.rdates) == len(ev.rdates)
    assert ev2.alarm_minutes == ev.alarm_minutes
    assert ev2.attendees[0].email == ev.attendees[0].email


def test_cache_preserves_all_day_events(tmp_path: Path) -> None:
    """All-day events (date, not datetime) should round-trip through cache."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="allday@example.com",
                summary="Holiday",
                dtstart=";VALUE=DATE:20250401",
                dtend=";VALUE=DATE:20250402",
            )
        ),
        filename="allday.ics",
    )

    db_path = tmp_path / "cache.db"
    ics_files = [(Path(cal_dir) / "personal" / "allday.ics", "personal")]

    events = cached_collect_events(ics_files, db_path=db_path)
    assert len(events) == 1
    ev = events[0]
    assert ev.is_all_day
    assert ev.dtstart == date(2025, 4, 1)
    assert ev.dtend == date(2025, 4, 2)

    # Round-trip through cache
    events2 = cached_collect_events(ics_files, db_path=db_path)
    assert events2[0].is_all_day
    assert events2[0].dtstart == date(2025, 4, 1)


def test_list_events_uses_cache(tmp_path: Path) -> None:
    """store.list_events should work transparently with the cache."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="list-cache@example.com",
                summary="Cached List",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
            )
        ),
        filename="event.ics",
    )

    # Set XDG_CACHE_HOME so the cache goes in tmp_path
    old_cache = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = str(tmp_path / "xdg-cache")
    try:
        events = store.list_events(
            calendars_dir=cal_dir,
            from_date=date(2025, 4, 1),
            to_date=date(2025, 4, 2),
        )
        assert len(events) == 1
        assert events[0].summary == "Cached List"
    finally:
        if old_cache is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = old_cache


def test_cache_handles_multiple_vevents_per_file(tmp_path: Path) -> None:
    """A single .ics with multiple VEVENTs (e.g. RECURRENCE-ID override)."""
    override_vevent = (
        "BEGIN:VEVENT\n"
        "UID:multi@example.com\n"
        "SUMMARY:Override\n"
        "DTSTART:20250408T090000Z\n"
        "DTEND:20250408T100000Z\n"
        "RECURRENCE-ID:20250408T090000Z\n"
        "END:VEVENT"
    )
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="multi@example.com",
                summary="Master",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
                vevent_lines=["RRULE:FREQ=WEEKLY;COUNT=3"],
                extra_components=override_vevent,
            )
        ),
        filename="multi.ics",
    )

    db_path = tmp_path / "cache.db"
    ics_files = [(Path(cal_dir) / "personal" / "multi.ics", "personal")]

    events = cached_collect_events(ics_files, db_path=db_path)
    # Should have 2 VEVENTs: master + override
    assert len(events) == 2
    uids = {ev.uid for ev in events}
    assert uids == {"multi@example.com"}
    summaries = {ev.summary for ev in events}
    assert "Master" in summaries
    assert "Override" in summaries
