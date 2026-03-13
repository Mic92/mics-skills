"""Tests for the calendar-cli invite command (send meeting invitations)."""

import email
import email.utils
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from calendar_cli.email_invite import _format_time_with_tz
from calendar_cli.main import main
from icalendar import Calendar

from .helpers import InviteArgs, extract_ics_from_email, run_invite


def _parse_email(path: Path) -> email.message.Message:
    return email.message_from_string(path.read_text())


def test_invite_email_structure(tmp_path: Path) -> None:
    """Test the email has correct headers, body, and ics attachment."""
    email_file = tmp_path / "invite.eml"

    result = run_invite(
        tmp_path,
        InviteArgs(
            summary="Project Review",
            attendees="alice@example.com,Bob <bob@example.com>",
            extra_args=["-d", "90", "--reminder", "30"],
            output_email=str(email_file),
        ),
    )

    assert result == 0
    msg = _parse_email(email_file)

    # Headers
    assert msg["Subject"] == "Invitation: Project Review"
    _, from_addr = email.utils.parseaddr(msg["From"])
    assert from_addr == "org@example.com"
    to_addrs = [addr for _, addr in email.utils.getaddresses([msg["To"]])]
    assert "alice@example.com" in to_addrs
    assert "bob@example.com" in to_addrs

    # Body text
    body = None
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body = part.get_payload(decode=True)
            assert isinstance(body, bytes)
            body = body.decode()
            break
    assert body is not None
    assert "Project Review" in body

    # Calendar attachment
    cal = extract_ics_from_email(msg.as_string())
    events = list(cal.walk("VEVENT"))
    assert len(events) == 1
    event = events[0]
    assert str(event["SUMMARY"]) == "Project Review"
    method = str(event["METHOD"]) if "METHOD" in event else str(cal["METHOD"])
    assert method == "REQUEST"

    # Alarm
    alarms = [c for c in event.subcomponents if c.name == "VALARM"]
    assert len(alarms) == 1


def test_invite_with_timezone(tmp_path: Path) -> None:
    """Test invite preserves timezone in the ics."""
    ics_file = tmp_path / "invite.ics"

    result = run_invite(
        tmp_path,
        InviteArgs(
            summary="Berlin Meeting",
            timezone="America/New_York",
            output_ics=str(ics_file),
        ),
    )

    assert result == 0
    cal = Calendar.from_ical(ics_file.read_text())
    event = next(iter(cal.walk("VEVENT")))
    assert str(event["SUMMARY"]) == "Berlin Meeting"
    dtstart = event["DTSTART"].dt
    assert "New_York" in str(dtstart.tzinfo)


def test_invite_with_recurrence(tmp_path: Path) -> None:
    """Test invite with rrule."""
    ics_file = tmp_path / "recurring.ics"

    result = run_invite(
        tmp_path,
        InviteArgs(
            summary="Weekly Meeting",
            extra_args=["--rrule", "FREQ=WEEKLY;COUNT=10"],
            output_ics=str(ics_file),
        ),
    )

    assert result == 0
    cal = Calendar.from_ical(ics_file.read_text())
    event = next(iter(cal.walk("VEVENT")))
    rrule = event["RRULE"]
    assert rrule["FREQ"] == ["WEEKLY"]
    assert rrule["COUNT"] == [10]


def test_invite_invalid_time_format(tmp_path: Path) -> None:
    """Test that invalid time format fails."""
    result = run_invite(tmp_path, InviteArgs(summary="Bad", start="invalid"))
    assert result == 1


def test_invite_missing_required_fields() -> None:
    """Test that missing required fields fail with argparse error."""
    # Missing --attendees
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "invite",
                "-s",
                "Test",
                "--start",
                "2024-03-20 14:00",
                "--timezone",
                "UTC",
                "--organizer-email",
                "test@example.com",
            ],
        )
    assert exc_info.value.code == 2

    # Missing --timezone
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "invite",
                "-s",
                "Test",
                "--start",
                "2024-03-20 14:00",
                "-a",
                "a@b.com",
                "--organizer-email",
                "test@example.com",
            ],
        )
    assert exc_info.value.code == 2


def test_invite_invalid_email_format(tmp_path: Path) -> None:
    """Test that invalid attendee email is rejected."""
    result = run_invite(tmp_path, InviteArgs(summary="Test", attendees="not-an-email"))
    assert result == 1


def test_invite_has_calscale_no_organizer_role(tmp_path: Path) -> None:
    """Invite includes CALSCALE:GREGORIAN and no ROLE on ORGANIZER (RFC 5545)."""
    ics_file = tmp_path / "rfc.ics"

    result = run_invite(
        tmp_path,
        InviteArgs(summary="RFC Test", output_ics=str(ics_file)),
    )

    assert result == 0
    raw = ics_file.read_bytes().decode()
    assert "CALSCALE:GREGORIAN" in raw
    # ROLE should only appear on ATTENDEE lines, not ORGANIZER
    for line in raw.splitlines():
        if "ORGANIZER" in line:
            assert "ROLE" not in line


def test_invite_output_email_stdout(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Test --output-email - writes parseable email to stdout."""
    result = run_invite(
        tmp_path,
        InviteArgs(summary="Stdout Test", output_email="-"),
    )

    assert result == 0
    out = capsys.readouterr().out
    msg = email.message_from_string(out)
    assert msg["Subject"] == "Invitation: Stdout Test"
    assert any(part.get_content_type() == "text/calendar" for part in msg.walk())


def test_invite_includes_vtimezone(tmp_path: Path) -> None:
    """Invites with non-UTC timezones should include a VTIMEZONE component."""
    eml = tmp_path / "tz-invite.eml"
    result = run_invite(
        tmp_path,
        InviteArgs(
            summary="TZ Invite",
            timezone="Europe/Berlin",
            output_email=str(eml),
        ),
    )
    assert result == 0

    msg = _parse_email(eml)
    cal = extract_ics_from_email(msg.as_string())
    assert cal is not None
    tzs = [c for c in cal.walk() if c.name == "VTIMEZONE"]
    assert len(tzs) >= 1

    # Also check CREATED property
    event = next(iter(cal.walk("VEVENT")))
    assert event.get("created") is not None


def test_invite_utc_no_vtimezone(tmp_path: Path) -> None:
    """UTC invites should not include a VTIMEZONE."""
    eml = tmp_path / "utc-invite.eml"
    result = run_invite(
        tmp_path,
        InviteArgs(summary="UTC Invite", output_email=str(eml)),
    )
    assert result == 0

    msg = _parse_email(eml)
    cal = extract_ics_from_email(msg.as_string())
    assert cal is not None
    tzs = [c for c in cal.walk() if c.name == "VTIMEZONE"]
    assert len(tzs) == 0


# ---------------------------------------------------------------------------
# _format_time_with_tz unit tests
# ---------------------------------------------------------------------------


def test_format_time_with_tz_utc() -> None:
    """Aware UTC datetime includes 'UTC' suffix."""
    dt = datetime(2024, 3, 20, 14, 0, tzinfo=ZoneInfo("UTC"))
    assert _format_time_with_tz(dt) == "02:00 PM UTC"


def test_format_time_with_tz_named() -> None:
    """Aware non-UTC datetime includes the timezone abbreviation."""
    dt = datetime(2024, 3, 20, 14, 0, tzinfo=ZoneInfo("America/New_York"))
    result = _format_time_with_tz(dt)
    # Should end with a tz abbreviation (EDT or EST depending on date)
    assert result.startswith("02:00 PM ")
    assert not result.endswith(" ")  # no trailing space


def test_format_time_with_tz_naive() -> None:
    """Naive datetime must not produce a trailing space."""
    dt = datetime(2024, 3, 20, 14, 0)  # noqa: DTZ001 — intentionally naive
    result = _format_time_with_tz(dt)
    assert result == "02:00 PM"
    assert not result.endswith(" ")
