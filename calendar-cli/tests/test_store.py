"""Tests for the calendar store (direct ics file manipulation)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from calendar_cli import store
from calendar_cli.errors import CalendarNotFoundError, InvalidInputError
from calendar_cli.timeutil import sanitize_timerange

from .helpers import ICSEvent, make_ics, setup_single_calendar


def test_discover_calendars(cal_dir: str) -> None:
    names = store.discover_calendars(cal_dir)
    assert "personal" in names
    assert "work" in names


def test_list_events_all(cal_dir: str) -> None:
    events = store.list_events(calendars_dir=cal_dir)
    assert len(events) == 4
    # Sorted by start time
    summaries = [e.summary for e in events]
    assert "Dentist appointment" in summaries
    assert "Sprint planning" in summaries


def test_list_events_filter_calendar(cal_dir: str) -> None:
    events = store.list_events(calendars_dir=cal_dir, calendar_filter="work")
    assert len(events) == 1
    assert events[0].summary == "Sprint planning"


def test_list_events_date_range(cal_dir: str) -> None:
    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 2),
        to_date=date(2025, 4, 3),  # exclusive end
    )
    summaries = [e.summary for e in events]
    # Sprint planning is on April 2, and the weekly standup (MO,WE,FR)
    # has a Wednesday occurrence on April 2 too.
    assert "Sprint planning" in summaries
    assert "Weekly standup" in summaries
    assert len(events) == 2


def test_list_events_date_range_excludes(cal_dir: str) -> None:
    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 10),
        to_date=date(2025, 4, 20),
    )
    # The weekly standup (MO,WE,FR, COUNT=10, starting April 1) has
    # occurrences on April 11 (Fri), 14 (Mon), 16 (Wed), 18 (Fri).
    assert len(events) == 4
    assert all(e.summary == "Weekly standup" for e in events)


def test_get_event(cal_dir: str) -> None:
    ev = store.get_event("event1-uid", cal_dir)
    assert ev is not None
    assert ev.summary == "Dentist appointment"
    assert ev.location == "Dr. Smith"
    assert ev.description == "Annual checkup"
    assert ev.calendar == "personal"


def test_get_event_not_found(cal_dir: str) -> None:
    ev = store.get_event("nonexistent-uid", cal_dir)
    assert ev is None


def test_get_event_all_day(cal_dir: str) -> None:
    ev = store.get_event("event2-uid", cal_dir)
    assert ev is not None
    assert ev.is_all_day
    assert ev.summary == "Company Holiday"


def test_get_event_recurring(cal_dir: str) -> None:
    ev = store.get_event("event3-uid", cal_dir)
    assert ev is not None
    assert "FREQ=WEEKLY" in ev.rrule
    assert len(ev.alarms) == 1


def test_create_event(cal_dir: str) -> None:
    tz = ZoneInfo("Europe/Berlin")
    start = datetime(2025, 5, 1, 10, 0, tzinfo=tz)
    end = datetime(2025, 5, 1, 11, 0, tzinfo=tz)

    ev = store.create_event(
        summary="New Meeting",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
        location="Room 42",
        description="Discuss project",
        alarm_minutes=[15, 60],
    )

    assert ev.summary == "New Meeting"
    assert ev.location == "Room 42"
    assert ev.filepath.exists()

    # Verify it can be read back
    ev2 = store.get_event(ev.uid, cal_dir)
    assert ev2 is not None
    assert ev2.summary == "New Meeting"
    assert ev2.location == "Room 42"
    assert ev2.description == "Discuss project"
    assert len(ev2.alarms) == 2


def test_create_event_unknown_calendar(cal_dir: str) -> None:
    """Creating an event in a non-existent calendar raises CalendarNotFoundError."""
    start = datetime(2025, 5, 1, 10, 0, tzinfo=UTC)
    end = datetime(2025, 5, 1, 11, 0, tzinfo=UTC)

    with pytest.raises(CalendarNotFoundError, match="does not exist"):
        store.create_event(
            summary="Test",
            dtstart=start,
            dtend=end,
            calendar_name="nonexistent",
            calendars_dir=cal_dir,
        )


def test_delete_event(cal_dir: str) -> None:
    assert store.delete_event("event1-uid", cal_dir)
    assert store.get_event("event1-uid", cal_dir) is None


def test_delete_event_not_found(cal_dir: str) -> None:
    assert not store.delete_event("nonexistent", cal_dir)


def test_update_event_summary(cal_dir: str) -> None:
    ev = store.update_event("event1-uid", cal_dir, summary="Updated title")
    assert ev is not None
    assert ev.summary == "Updated title"

    # Other fields preserved
    ev2 = store.get_event("event1-uid", cal_dir)
    assert ev2 is not None
    assert ev2.summary == "Updated title"
    assert ev2.location == "Dr. Smith"


def test_update_event_time(cal_dir: str) -> None:
    new_start = datetime(2025, 4, 5, 14, 0, tzinfo=UTC)
    new_end = datetime(2025, 4, 5, 15, 0, tzinfo=UTC)
    ev = store.update_event("event1-uid", cal_dir, dtstart=new_start, dtend=new_end)
    assert ev is not None
    assert ev.dtstart == new_start
    assert ev.dtend == new_end


def test_update_event_not_found(cal_dir: str) -> None:
    ev = store.update_event("nonexistent", cal_dir, summary="Nope")
    assert ev is None


def test_update_event_location(cal_dir: str) -> None:
    ev = store.update_event("event1-uid", cal_dir, location="New Office")
    assert ev is not None
    assert ev.location == "New Office"
    # Summary preserved
    assert ev.summary == "Dentist appointment"


def test_create_event_with_rrule(cal_dir: str) -> None:
    start = datetime(2025, 5, 1, 9, 0, tzinfo=UTC)
    end = datetime(2025, 5, 1, 9, 30, tzinfo=UTC)

    ev = store.create_event(
        summary="Daily sync",
        dtstart=start,
        dtend=end,
        calendar_name="work",
        calendars_dir=cal_dir,
        rrule="FREQ=DAILY;COUNT=5",
    )

    ev2 = store.get_event(ev.uid, cal_dir)
    assert ev2 is not None
    assert "FREQ=DAILY" in ev2.rrule


def test_empty_calendar_dir(tmp_path: Path) -> None:
    events = store.list_events(calendars_dir=str(tmp_path))
    assert events == []

    names = store.discover_calendars(str(tmp_path))
    assert names == []


def test_nonexistent_calendar_dir(tmp_path: Path) -> None:
    fake = str(tmp_path / "does-not-exist")
    assert store.list_events(calendars_dir=fake) == []
    assert store.discover_calendars(fake) == []
    assert store.get_event("x", fake) is None
    assert not store.delete_event("x", fake)


def test_sanitize_timerange_equal() -> None:
    """DTEND == DTSTART gets bumped to +1h."""
    start = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
    _, e = sanitize_timerange(start, start)
    assert e == start + timedelta(hours=1)


def test_sanitize_timerange_swapped() -> None:
    """DTEND < DTSTART gets swapped."""
    early = datetime(2025, 6, 1, 9, 0, tzinfo=UTC)
    late = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
    s, e = sanitize_timerange(late, early)
    assert s == early
    assert e == late


def test_read_event_missing_dtend(tmp_path: Path) -> None:
    """Events without DTEND get a synthesized end time."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="no-end@example.com",
                summary="No End Time",
                dtstart="20250601T100000Z",
                dtend=None,
            )
        ),
        filename="no-end.ics",
    )

    events = store.list_events(calendars_dir=cal_dir)
    assert len(events) == 1
    assert events[0].dtend == datetime(2025, 6, 1, 11, 0, tzinfo=UTC)


def test_create_event_has_calscale_and_sequence(cal_dir: str) -> None:
    """New events include CALSCALE:GREGORIAN and SEQUENCE:0 per RFC 5545."""
    start = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
    end = datetime(2025, 6, 1, 11, 0, tzinfo=UTC)
    ev = store.create_event(
        summary="RFC Test",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
    )
    raw = ev.filepath.read_bytes().decode()
    assert "CALSCALE:GREGORIAN" in raw
    assert "SEQUENCE:0" in raw
    assert "LAST-MODIFIED:" in raw


def test_update_increments_sequence(cal_dir: str) -> None:
    """Editing an event increments SEQUENCE (RFC 5545 §3.8.7.4)."""
    start = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
    end = datetime(2025, 6, 1, 11, 0, tzinfo=UTC)
    ev = store.create_event(
        summary="Seq Test",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
    )
    raw0 = ev.filepath.read_bytes().decode()
    assert "SEQUENCE:0" in raw0

    store.update_event(ev.uid, cal_dir, summary="Seq Test v2")
    raw1 = ev.filepath.read_bytes().decode()
    assert "SEQUENCE:1" in raw1

    store.update_event(ev.uid, cal_dir, summary="Seq Test v3")
    raw2 = ev.filepath.read_bytes().decode()
    assert "SEQUENCE:2" in raw2


def test_update_preserves_all_day(cal_dir: str) -> None:
    """Editing an all-day event preserves DATE type (not coerced to DATETIME)."""
    start = date(2025, 12, 25)
    end = date(2025, 12, 26)
    ev = store.create_event(
        summary="Holiday",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
    )
    updated = store.update_event(ev.uid, cal_dir, summary="Christmas")
    assert updated is not None
    assert updated.is_all_day
    assert isinstance(updated.dtstart, date)
    assert not isinstance(updated.dtstart, datetime)


def test_read_attendees_and_organizer(tmp_path: Path) -> None:
    """Attendees, organizer, status, and URL are parsed from .ics files."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="meeting-with-people@example.com",
                summary="Team Sync",
                dtstart="20250601T140000Z",
                dtend="20250601T150000Z",
                vevent_lines=[
                    "STATUS:CONFIRMED",
                    "URL:https://meet.example.com/team",
                    "ORGANIZER;CN=Alice:mailto:alice@example.com",
                    "ATTENDEE;CN=Bob;PARTSTAT=ACCEPTED:mailto:bob@example.com",
                    "ATTENDEE;CN=Carol;PARTSTAT=TENTATIVE:mailto:carol@example.com",
                    "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:dave@example.com",
                ],
            )
        ),
        filename="meeting.ics",
    )

    ev = store.get_event("meeting-with-people@example.com", cal_dir)
    assert ev is not None
    assert ev.status == "CONFIRMED"
    assert ev.url == "https://meet.example.com/team"
    assert ev.organizer == "Alice (alice@example.com)"
    assert len(ev.attendees) == 3
    assert ev.attendees[0].name == "Bob"
    assert ev.attendees[0].email == "bob@example.com"
    assert ev.attendees[0].status == "ACCEPTED"
    assert str(ev.attendees[0]) == "Bob (accepted)"
    assert str(ev.attendees[1]) == "Carol (tentative)"
    assert str(ev.attendees[2]) == "dave@example.com"  # no name, needs-action


def test_sanitize_timerange_mixed_date_datetime(tmp_path: Path) -> None:
    """Malformed ICS with DATE dtstart and DATETIME dtend must not crash."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="mixed-types@example.com",
                summary="Mixed Types",
                dtstart=";VALUE=DATE:20250401",
                dtend="20250401T170000Z",
            )
        ),
        filename="mixed.ics",
    )

    events = store.list_events(calendars_dir=cal_dir)
    assert len(events) == 1
    ev = events[0]
    assert ev.summary == "Mixed Types"
    # The coerced types should be comparable without TypeError
    assert ev.dtend is not None
    assert ev.dtend >= ev.dtstart


def test_sanitize_timerange_mixed_datetime_date() -> None:
    """datetime DTSTART + date DTEND should not crash."""
    dtstart = datetime(2025, 4, 1, 10, 0, tzinfo=UTC)
    dtend_date = date(2025, 4, 2)
    # Must not raise TypeError
    s, e = sanitize_timerange(dtstart, dtend_date)
    assert isinstance(s, datetime)
    assert isinstance(e, datetime)


def test_sanitize_timerange_mixed_date_datetime_swapped() -> None:
    """Mixed types with DTEND < DTSTART should be swapped, not crash."""
    dtstart_date = date(2025, 4, 5)
    dtend = datetime(2025, 4, 1, 10, 0, tzinfo=UTC)
    s, e = sanitize_timerange(dtstart_date, dtend)
    # After coercion and swap, start <= end
    assert s <= e


def test_rrule_expansion_in_date_range(tmp_path: Path) -> None:
    """Recurring events should appear for each occurrence within the date range."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="weekly@example.com",
                summary="Weekly Standup",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
                vevent_lines=["RRULE:FREQ=WEEKLY;COUNT=5"],
            )
        ),
        filename="weekly.ics",
    )

    # Ask for the second week only — should see one occurrence on April 8
    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 7),
        to_date=date(2025, 4, 9),
    )
    assert len(events) == 1
    assert events[0].summary == "Weekly Standup"
    assert isinstance(events[0].dtstart, datetime)
    assert events[0].dtstart.date() == date(2025, 4, 8)


def test_rrule_expansion_with_exdate(tmp_path: Path) -> None:
    """EXDATE exclusions should suppress the matching occurrence."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="exdate@example.com",
                summary="Weekly with skip",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
                vevent_lines=[
                    "RRULE:FREQ=WEEKLY;COUNT=5",
                    "EXDATE:20250408T090000Z",
                ],
            )
        ),
        filename="weekly-exdate.ics",
    )

    # April 7-16: should see April 15 only (April 8 excluded)
    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 7),
        to_date=date(2025, 4, 16),
    )
    assert len(events) == 1
    assert events[0].dtstart.date() == date(2025, 4, 15)  # type: ignore[union-attr]


def test_rrule_expansion_recurrence_id_override(tmp_path: Path) -> None:
    """A VEVENT with RECURRENCE-ID overrides the matching RRULE occurrence."""
    override_vevent = (
        "BEGIN:VEVENT\n"
        "UID:override@example.com\n"
        "RECURRENCE-ID:20250408T090000Z\n"
        "DTSTART:20250408T100000Z\n"
        "DTEND:20250408T110000Z\n"
        "SUMMARY:Weekly Meeting (rescheduled)\n"
        "END:VEVENT"
    )
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="override@example.com",
                summary="Weekly Meeting",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
                vevent_lines=["RRULE:FREQ=WEEKLY;COUNT=5"],
                extra_components=override_vevent,
            )
        ),
        filename="weekly-override.ics",
    )

    # April 7-9: should see the rescheduled version
    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 7),
        to_date=date(2025, 4, 9),
    )
    assert len(events) == 1
    assert events[0].summary == "Weekly Meeting (rescheduled)"
    assert events[0].dtstart.hour == 10  # type: ignore[union-attr]


def test_rrule_all_day_expansion(tmp_path: Path) -> None:
    """All-day recurring events should also be expanded."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="allday-recur@example.com",
                summary="Monthly Review",
                dtstart=";VALUE=DATE:20250101",
                dtend=";VALUE=DATE:20250102",
                vevent_lines=["RRULE:FREQ=MONTHLY;COUNT=12"],
            )
        ),
        filename="monthly-allday.ics",
    )

    # March: should see one occurrence
    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 3, 1),
        to_date=date(2025, 3, 31),
    )
    assert len(events) == 1
    assert events[0].summary == "Monthly Review"
    assert events[0].dtstart == date(2025, 3, 1)


def test_sanitize_timerange_negative_duration() -> None:
    """Negative DURATION should not produce dtend < dtstart."""
    dtstart = datetime(2025, 4, 1, 10, 0, tzinfo=UTC)
    s, e = sanitize_timerange(dtstart, None, duration=timedelta(minutes=-30))
    assert e >= s


def test_read_event_negative_duration(tmp_path: Path) -> None:
    """Events with negative DURATION should get a corrected time range."""
    cal_dir = setup_single_calendar(
        tmp_path,
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\n"
        "UID:neg-dur@example.com\n"
        "DTSTART:20250401T100000Z\n"
        "DURATION:-PT30M\n"
        "SUMMARY:Negative Duration\n"
        "END:VEVENT\nEND:VCALENDAR",
        filename="neg-dur.ics",
    )

    events = store.list_events(calendars_dir=cal_dir)
    assert len(events) == 1
    ev = events[0]
    assert ev.dtend is not None
    assert ev.dtend >= ev.dtstart


# ---------------------------------------------------------------------------
# Issue #4: update_event preserves properties
# ---------------------------------------------------------------------------


def test_update_preserves_attendees_and_organizer(tmp_path: Path) -> None:
    """Editing summary must not destroy ORGANIZER, ATTENDEE, STATUS, or URL."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="preserve-test@example.com",
                summary="Original Title",
                dtstart="20250601T140000Z",
                dtend="20250601T150000Z",
                vevent_lines=[
                    "STATUS:CONFIRMED",
                    "URL:https://meet.example.com/team",
                    "ORGANIZER;CN=Alice:mailto:alice@example.com",
                    "ATTENDEE;CN=Bob;PARTSTAT=ACCEPTED:mailto:bob@example.com",
                    "ATTENDEE;CN=Carol;PARTSTAT=TENTATIVE:mailto:carol@example.com",
                    "SEQUENCE:0",
                ],
            )
        ),
        filename="meeting.ics",
    )

    ev = store.update_event(
        "preserve-test@example.com", cal_dir, summary="Renamed Meeting"
    )
    assert ev is not None
    assert ev.summary == "Renamed Meeting"
    assert ev.status == "CONFIRMED"
    assert ev.url == "https://meet.example.com/team"
    assert ev.organizer == "Alice (alice@example.com)"
    assert len(ev.attendees) == 2
    assert ev.attendees[0].name == "Bob"
    assert ev.attendees[0].status == "ACCEPTED"

    # Verify SEQUENCE was incremented
    raw = ev.filepath.read_bytes().decode()
    assert "SEQUENCE:1" in raw


# ---------------------------------------------------------------------------
# Issue #6: Multi-day events visible when querying middle days
# ---------------------------------------------------------------------------


def test_multiday_event_visible_on_middle_day(tmp_path: Path) -> None:
    """A 3-day event starting April 1 should appear when querying April 2."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="conference@example.com",
                summary="3-Day Conference",
                dtstart="20250401T090000Z",
                dtend="20250403T170000Z",
            )
        ),
        filename="conference.ics",
    )

    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 2),
        to_date=date(2025, 4, 3),
    )
    assert len(events) == 1
    assert events[0].summary == "3-Day Conference"


def test_multiday_allday_event_visible_on_middle_day(tmp_path: Path) -> None:
    """A multi-day all-day event should appear on all days it spans."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="vacation@example.com",
                summary="Vacation",
                dtstart=";VALUE=DATE:20250401",
                dtend=";VALUE=DATE:20250404",
            )
        ),
        filename="vacation.ics",
    )

    # Query only April 2-3 — vacation spans April 1-3 (DTEND exclusive)
    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 2),
        to_date=date(2025, 4, 3),
    )
    assert len(events) == 1
    assert events[0].summary == "Vacation"


def test_event_ending_before_range_not_shown(tmp_path: Path) -> None:
    """An event ending before the query range should not appear."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="past@example.com",
                summary="Past Event",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
            )
        ),
        filename="past.ics",
    )

    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 2),
        to_date=date(2025, 4, 3),
    )
    assert len(events) == 0


# ---------------------------------------------------------------------------
# Issue #2: RDATE support
# ---------------------------------------------------------------------------


def test_rrule_expansion_with_rdate(tmp_path: Path) -> None:
    """RDATE adds extra occurrences beyond the RRULE pattern."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="rdate@example.com",
                summary="With RDATE",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
                vevent_lines=[
                    "RRULE:FREQ=WEEKLY;COUNT=2",
                    "RDATE:20250410T090000Z",
                ],
            )
        ),
        filename="rdate.ics",
    )

    # RRULE gives April 1 and 8; RDATE adds April 10
    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 1),
        to_date=date(2025, 4, 11),
    )
    assert len(events) == 3
    dates = [e.dtstart.date() for e in events]  # type: ignore[union-attr]
    assert date(2025, 4, 1) in dates
    assert date(2025, 4, 8) in dates
    assert date(2025, 4, 10) in dates


def test_rrule_with_utc_until(tmp_path: Path) -> None:
    """RRULE UNTIL with Z suffix must not crash when dtstart is tz-aware.

    dateutil requires UNTIL and DTSTART to have matching tz-awareness.
    Since we strip tzinfo from DTSTART for rrule expansion, we must
    also strip the Z (UTC) from UNTIL in the RRULE string.
    """
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="until-utc@example.com",
                summary="Recurring with UNTIL Z",
                dtstart=";TZID=Europe/Berlin:20250401T090000",
                dtend=";TZID=Europe/Berlin:20250401T100000",
                vevent_lines=[
                    "RRULE:FREQ=WEEKLY;UNTIL=20250422T070000Z",
                ],
            )
        ),
        filename="until-utc.ics",
    )

    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 1),
        to_date=date(2025, 4, 23),
    )
    assert len(events) >= 1
    assert events[0].summary == "Recurring with UNTIL Z"
    # Should have weekly occurrences: Apr 1, 8, 15, 22
    dates = [e.dtstart.date() for e in events]  # type: ignore[union-attr]
    assert date(2025, 4, 1) in dates
    assert date(2025, 4, 8) in dates
    assert date(2025, 4, 15) in dates


# ---------------------------------------------------------------------------
# Issue #8: Absolute alarm triggers
# ---------------------------------------------------------------------------


def test_absolute_alarm_trigger(tmp_path: Path) -> None:
    """Absolute TRIGGER (VALUE=DATE-TIME) should not crash."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="abs-alarm@example.com",
                summary="Absolute Alarm",
                dtstart="20250401T140000Z",
                dtend="20250401T150000Z",
                vevent_lines=[
                    "BEGIN:VALARM",
                    "TRIGGER;VALUE=DATE-TIME:20250401T133000Z",
                    "ACTION:DISPLAY",
                    "DESCRIPTION:Reminder",
                    "END:VALARM",
                ],
            )
        ),
        filename="abs-alarm.ics",
    )

    events = store.list_events(calendars_dir=cal_dir)
    assert len(events) == 1
    ev = events[0]
    # 14:00 - 13:30 = 30 minutes before
    assert ev.alarm_minutes == [30]
    assert ev.alarms == ["30m before"]


def test_alarm_related_end_absolute(tmp_path: Path) -> None:
    """Absolute TRIGGER with RELATED=END computes offset from DTEND."""
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="rel-end-abs@example.com",
                summary="Related End Abs",
                dtstart="20250401T140000Z",
                dtend="20250401T150000Z",
                vevent_lines=[
                    "BEGIN:VALARM",
                    "TRIGGER;VALUE=DATE-TIME;RELATED=END:20250401T144500Z",
                    "ACTION:DISPLAY",
                    "DESCRIPTION:Reminder",
                    "END:VALARM",
                ],
            )
        ),
        filename="rel-end-abs.ics",
    )

    events = store.list_events(calendars_dir=cal_dir)
    assert len(events) == 1
    ev = events[0]
    # 15:00 (DTEND) - 14:45 (trigger) = 15 minutes before end
    assert ev.alarm_minutes == [15]


# ---------------------------------------------------------------------------
# Issue #1: VTIMEZONE in created events
# ---------------------------------------------------------------------------


def test_create_event_includes_vtimezone(cal_dir: str) -> None:
    """Events with non-UTC timezones should include a VTIMEZONE component."""
    tz = ZoneInfo("Europe/Berlin")
    start = datetime(2025, 5, 1, 10, 0, tzinfo=tz)
    end = datetime(2025, 5, 1, 11, 0, tzinfo=tz)

    ev = store.create_event(
        summary="TZ Test",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
    )

    raw = ev.filepath.read_bytes().decode()
    assert "BEGIN:VTIMEZONE" in raw
    assert "Europe/Berlin" in raw


def test_create_event_utc_no_vtimezone(cal_dir: str) -> None:
    """UTC events should not include a VTIMEZONE (UTC needs no definition)."""
    start = datetime(2025, 5, 1, 10, 0, tzinfo=UTC)
    end = datetime(2025, 5, 1, 11, 0, tzinfo=UTC)

    ev = store.create_event(
        summary="UTC Test",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
    )

    raw = ev.filepath.read_bytes().decode()
    assert "BEGIN:VTIMEZONE" not in raw


# ---------------------------------------------------------------------------
# Issue #9: CREATED property
# ---------------------------------------------------------------------------


def test_create_event_has_created(cal_dir: str) -> None:
    """New events include CREATED per RFC 5545 §3.8.7.1."""
    start = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
    end = datetime(2025, 6, 1, 11, 0, tzinfo=UTC)
    ev = store.create_event(
        summary="Created Test",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
    )
    raw = ev.filepath.read_bytes().decode()
    assert "CREATED:" in raw


# ---------------------------------------------------------------------------
# Issue #3: RECURRENCE-ID matched by exact datetime
# ---------------------------------------------------------------------------


def test_recurrence_id_exact_datetime_match(tmp_path: Path) -> None:
    """RECURRENCE-ID overrides should match by exact datetime, not just date."""
    override_vevent = (
        "BEGIN:VEVENT\n"
        "UID:twice-daily@example.com\n"
        "RECURRENCE-ID:20250401T150000Z\n"
        "DTSTART:20250401T160000Z\n"
        "DTEND:20250401T170000Z\n"
        "SUMMARY:Twice Daily (moved)\n"
        "END:VEVENT"
    )
    cal_dir = setup_single_calendar(
        tmp_path,
        make_ics(
            ICSEvent(
                uid="twice-daily@example.com",
                summary="Twice Daily",
                dtstart="20250401T090000Z",
                dtend="20250401T100000Z",
                vevent_lines=["RRULE:FREQ=DAILY;BYHOUR=9,15;COUNT=4"],
                extra_components=override_vevent,
            )
        ),
        filename="twice-daily.ics",
    )

    events = store.list_events(
        calendars_dir=cal_dir,
        from_date=date(2025, 4, 1),
        to_date=date(2025, 4, 2),
    )
    summaries = [e.summary for e in events]
    # The 09:00 occurrence should still be present
    assert "Twice Daily" in summaries
    # The 15:00 occurrence should be replaced
    assert "Twice Daily (moved)" in summaries


# ---------------------------------------------------------------------------
# search_events
# ---------------------------------------------------------------------------


def test_search_events_matches_summary_location_description(cal_dir: str) -> None:
    """search_events matches across summary, location, and description."""
    # Match by summary (case-insensitive)
    assert len(store.search_events("dentist", calendars_dir=cal_dir)) == 1
    # Match by description
    assert len(store.search_events("annual", calendars_dir=cal_dir)) == 1
    # No match
    assert store.search_events("xyznonexistent", calendars_dir=cal_dir) == []


def test_search_events_calendar_filter(cal_dir: str) -> None:
    """search_events respects calendar_filter."""
    assert (
        len(
            store.search_events(
                "planning", calendars_dir=cal_dir, calendar_filter="work"
            )
        )
        == 1
    )
    assert (
        store.search_events(
            "planning", calendars_dir=cal_dir, calendar_filter="personal"
        )
        == []
    )


def test_search_events_deduplicates_recurring(cal_dir: str) -> None:
    """Recurring events appear once in search results, not per occurrence."""
    results = store.search_events("standup", calendars_dir=cal_dir)
    assert len(results) == 1
    assert results[0].uid == "event3-uid"


def test_search_events_regex(cal_dir: str) -> None:
    """search_events supports regex patterns."""
    # Alternation: match either dentist or sprint
    results = store.search_events("dentist|sprint", calendars_dir=cal_dir)
    summaries = {e.summary for e in results}
    assert "Dentist appointment" in summaries
    assert "Sprint planning" in summaries


def test_search_events_invalid_regex(cal_dir: str) -> None:
    """Invalid regex raises InvalidInputError."""
    with pytest.raises(InvalidInputError):
        store.search_events("[invalid", calendars_dir=cal_dir)
