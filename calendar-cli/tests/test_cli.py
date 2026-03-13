"""Tests for the calendar-cli command-line interface.

Only covers CLI-specific logic (arg parsing, output formatting, sync wiring)
that isn't already tested by test_store.py.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from calendar_cli import store
from calendar_cli.main import main
from calendar_cli.timeutil import parse_datetime

from .helpers import run_cli


def test_calendars_smoke(cal_dir: str, capsys: pytest.CaptureFixture[str]) -> None:
    result = run_cli(cal_dir, "calendars")
    assert result == 0
    out = capsys.readouterr().out
    assert "personal" in out
    assert "work" in out


def test_list_verbose_shows_details(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run_cli(
        cal_dir, "list", "-v", "--from", "2025-04-01", "--to", "2025-04-02"
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "Room 5" in out or "Dr. Smith" in out
    assert "Weekly sync" in out or "Annual checkup" in out


def test_new_event_alarm_parsing(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run_cli(
        cal_dir,
        "new",
        "Alarm Test",
        "--start",
        "2025-05-01 10:00",
        "--timezone",
        "Europe/Berlin",
        "-d",
        "30",
        "--alarm",
        "15m",
        "--alarm",
        "1h",
        "-c",
        "personal",
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "Alarm Test" in out


@pytest.mark.parametrize("bad_spec", ["m", "xh", "abc", ""])
def test_new_event_bad_alarm_spec(
    cal_dir: str,
    capsys: pytest.CaptureFixture[str],
    bad_spec: str,
) -> None:
    """Malformed alarm specs produce a clean error, not a traceback."""
    result = run_cli(
        cal_dir,
        "new",
        "Alarm Fail",
        "--start",
        "2025-05-01 10:00",
        "--timezone",
        "UTC",
        "--alarm",
        bad_spec,
    )
    assert result == 1
    err = capsys.readouterr().err
    assert "Invalid alarm spec" in err


@pytest.mark.parametrize("bad_date", ["+d", "+xd", "not-a-date"])
def test_list_bad_date(
    cal_dir: str,
    capsys: pytest.CaptureFixture[str],
    bad_date: str,
) -> None:
    """Malformed --from values produce a clean error, not a traceback."""
    result = run_cli(cal_dir, "list", "--from", bad_date)
    assert result == 1
    err = capsys.readouterr().err
    assert "Error" in err


def test_new_event_bad_time(cal_dir: str, capsys: pytest.CaptureFixture[str]) -> None:
    result = run_cli(
        cal_dir,
        "new",
        "Bad time",
        "--start",
        "not-a-date",
        "--timezone",
        "UTC",
    )
    assert result == 1
    err = capsys.readouterr().err
    assert "Error" in err


def test_new_event_requires_timezone(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run_cli(
        cal_dir,
        "new",
        "No TZ",
        "--start",
        "2025-05-01 10:00",
    )
    assert result == 1
    err = capsys.readouterr().err
    assert "--timezone is required" in err


def test_edit_requires_timezone_for_time_changes(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run_cli(cal_dir, "edit", "meeting-uid", "--start", "2025-04-02 10:00")
    assert result == 1
    err = capsys.readouterr().err
    assert "--timezone is required" in err


def test_no_sync_flag(cal_dir: str) -> None:
    with patch("calendar_cli.main.subprocess.run") as mock_run:
        result = run_cli(cal_dir, "list", "--from", "2025-04-01", "--to", "2025-04-02")
        assert result == 0
        mock_run.assert_not_called()


def test_new_event_iso_datetime(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """ISO 8601 T separator is accepted in --start/--end."""
    result = run_cli(
        cal_dir,
        "new",
        "ISO Test",
        "--start",
        "2025-05-01T10:00",
        "--timezone",
        "Europe/Berlin",
        "-c",
        "personal",
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "ISO Test" in out


def test_new_all_day_event(cal_dir: str, capsys: pytest.CaptureFixture[str]) -> None:
    """--all-day creates a date-only event without requiring --timezone."""
    result = run_cli(
        cal_dir,
        "new",
        "Holiday",
        "--start",
        "2025-12-25",
        "--all-day",
        "-c",
        "personal",
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "Holiday" in out
    assert "2025-12-25" in out


def test_case_insensitive_calendar(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Calendar names are resolved case-insensitively."""
    # The fixture creates 'personal' and 'work' directories (lowercase)
    result = run_cli(
        cal_dir, "list", "-c", "Personal", "--from", "2025-04-01", "--to", "2025-04-02"
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "Dentist appointment" in out


def test_alarm_display(cal_dir: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Alarms display as human-readable '15m before' not raw timedelta."""
    result = run_cli(
        cal_dir,
        "new",
        "Alarm Display",
        "--start",
        "2025-05-01T10:00",
        "--timezone",
        "Europe/Berlin",
        "--alarm",
        "15m",
        "-c",
        "personal",
    )
    assert result == 0
    # Read back with verbose to see alarm display
    capsys.readouterr()  # clear

    events = store.list_events(calendars_dir=cal_dir)
    alarm_event = next(e for e in events if e.summary == "Alarm Display")
    assert alarm_event.alarms == ["15m before"]


def test_update_preserves_alarms(cal_dir: str) -> None:
    """Editing summary should not erase existing alarms."""

    start = datetime(2025, 5, 1, 10, 0, tzinfo=UTC)
    end = datetime(2025, 5, 1, 11, 0, tzinfo=UTC)
    ev = store.create_event(
        summary="Keep Alarms",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
        alarm_minutes=[15, 60],
    )
    updated = store.update_event(ev.uid, cal_dir, summary="Renamed")
    assert updated is not None
    assert updated.alarm_minutes == [15, 60]
    assert updated.alarms == ["15m before", "1h before"]


def test_parse_datetime_dst_gap() -> None:
    """Time in a DST gap (spring-forward) must get the post-transition offset."""
    dt = parse_datetime("2025-03-09 02:30", "America/New_York")
    # In the gap, 02:30 should become EDT (UTC-4), not EST (UTC-5)
    assert dt.utcoffset() == timedelta(hours=-4)


def test_parse_datetime_dst_fall_back() -> None:
    """Ambiguous time (fall-back) should resolve to the first occurrence."""
    dt = parse_datetime("2025-11-02 01:30", "America/New_York")
    # First occurrence = EDT (UTC-4)
    assert dt.utcoffset() == timedelta(hours=-4)


def test_new_event_during_dst_gap(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Creating an event during a DST gap should succeed with correct offset."""
    result = run_cli(
        cal_dir,
        "new",
        "DST Gap Meeting",
        "--start",
        "2025-03-09 02:30",
        "--timezone",
        "America/New_York",
        "-c",
        "personal",
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "DST Gap Meeting" in out


def test_all_day_end_equals_start(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--all-day with --end equal to --start should produce a 1-day event."""
    result = run_cli(
        cal_dir,
        "new",
        "Single Day",
        "--start",
        "2025-04-01",
        "--end",
        "2025-04-01",
        "--all-day",
        "-c",
        "personal",
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "Single Day" in out

    # Verify DTEND was bumped
    events = store.list_events(calendars_dir=cal_dir)
    ev = next(e for e in events if e.summary == "Single Day")

    assert str(ev.dtstart) == "2025-04-01"
    assert str(ev.dtend) == "2025-04-02"


def test_all_day_end_before_start(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--all-day with --end before --start should error."""
    result = run_cli(
        cal_dir,
        "new",
        "Bad Range",
        "--start",
        "2025-04-05",
        "--end",
        "2025-04-01",
        "--all-day",
        "-c",
        "personal",
    )
    assert result == 1
    err = capsys.readouterr().err
    assert "end" in err.lower() or "before" in err.lower() or "Error" in err


def test_global_flags_after_subcommand(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Global flags like --calendar-dir work after the subcommand."""
    result = main(["calendars", "--calendar-dir", cal_dir])
    assert result == 0
    out = capsys.readouterr().out
    assert "personal" in out


def test_search_limit(cal_dir: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Search respects --limit."""
    result = run_cli(cal_dir, "search", "e", "--limit", "1")
    assert result == 0
    out = capsys.readouterr().out
    assert "more event(s) not shown" in out


def test_list_limit_truncates(cal_dir: str, capsys: pytest.CaptureFixture[str]) -> None:
    """--limit caps displayed events and shows a remainder message."""
    result = run_cli(
        cal_dir, "list", "--from", "2025-04-01", "--to", "2025-04-30", "--limit", "2"
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "more event(s) not shown" in out


def test_list_limit_zero_shows_all(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """--limit 0 disables truncation."""
    result = run_cli(
        cal_dir, "list", "--from", "2025-04-01", "--to", "2025-04-30", "--limit", "0"
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "more event(s) not shown" not in out


def test_list_verbose_shows_day_headers(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verbose list groups events under day headers on their own line."""
    # The fixture has events on 2025-04-01 and 2025-04-02
    result = run_cli(
        cal_dir, "list", "-v", "--from", "2025-04-01", "--to", "2025-04-03"
    )
    assert result == 0
    out = capsys.readouterr().out
    # Day headers must be standalone lines (not part of an event line)
    lines = [line.strip() for line in out.splitlines()]
    assert "Tue 2025-04-01:" in lines
    assert "Wed 2025-04-02:" in lines


def test_list_verbose_truncates_description(
    cal_dir: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verbose list truncates long descriptions; show gives full text."""
    # Create an event with a long description
    start = datetime(2025, 5, 1, 10, 0, tzinfo=UTC)
    end = datetime(2025, 5, 1, 11, 0, tzinfo=UTC)
    long_desc = "A" * 300
    ev = store.create_event(
        summary="Long Desc",
        dtstart=start,
        dtend=end,
        calendar_name="personal",
        calendars_dir=cal_dir,
        description=long_desc,
    )

    # list -v should truncate
    run_cli(cal_dir, "list", "-v", "--from", "2025-05-01", "--to", "2025-05-02")
    out = capsys.readouterr().out
    assert "…" in out
    assert long_desc not in out

    # show should give full text
    run_cli(cal_dir, "show", ev.uid)
    out = capsys.readouterr().out
    assert long_desc in out
    assert "…" not in out
