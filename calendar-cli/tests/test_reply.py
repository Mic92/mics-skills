"""Test cases for the vcal reply command."""

import email.utils
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from calendar_cli.import_invite import import_to_local
from calendar_cli.main import main
from icalendar import Calendar

from .helpers import (
    EmailInvite,
    ICSEvent,
    make_email_invite,
    make_ics,
    parse_reply_email,
)


def _write_invite(tmp_path: Path, invite: EmailInvite) -> Path:
    """Write an email invite file and return its path."""
    path = tmp_path / f"{invite.uid}.ics"
    path.write_text(make_email_invite(invite))
    return path


def test_reply_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test dry-run prints reply details without sending."""
    invite = _write_invite(
        tmp_path,
        EmailInvite(uid="dry-run@example.com", summary="Dry Run Meeting"),
    )

    result = main(["reply", "accept", "--dry-run", str(invite)])

    assert result == 0
    out = capsys.readouterr().out
    assert "Would send reply to: organizer@example.com" in out
    assert "Status: ACCEPTED" in out
    assert "METHOD:REPLY" in out


@patch("calendar_cli.reply.subprocess.run")
def test_reply_send_via_email(mock_run: MagicMock, tmp_path: Path) -> None:
    """Test sending reply via msmtp produces valid email with ics attachment."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    invite = _write_invite(
        tmp_path,
        EmailInvite(
            uid="email-test@example.com",
            to="testuser@example.com",
            summary="Email Reply Test",
            organizer="mailto:organizer@example.com",
        ),
    )

    result = main(["reply", "accept", str(invite)])
    assert result == 0

    mock_run.assert_called_once()
    raw = mock_run.call_args[1]["input"]
    msg, cal = parse_reply_email(raw)

    # Email headers
    _, from_addr = email.utils.parseaddr(msg["From"])
    assert from_addr == "testuser@example.com"
    _, to_addr = email.utils.parseaddr(msg["To"])
    assert to_addr == "organizer@example.com"
    assert "Accepted" in msg["Subject"]

    # Calendar attachment
    assert str(cal["METHOD"]) == "REPLY"
    event = next(iter(cal.walk("VEVENT")))
    assert str(event["UID"]) == "email-test@example.com"
    attendees = event.get("ATTENDEE")
    # Single attendee comes back as vCalAddress, not list
    if isinstance(attendees, list):
        partstat = attendees[0].params.get("PARTSTAT")
    else:
        partstat = attendees.params.get("PARTSTAT")
    assert partstat == "ACCEPTED"


def test_reply_with_comment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test reply includes COMMENT in the ics."""
    invite = _write_invite(
        tmp_path,
        EmailInvite(uid="comment@example.com", summary="Comment Test"),
    )

    result = main(
        [
            "reply",
            "tentative",
            "--comment",
            "I might be 10 minutes late",
            "--dry-run",
            str(invite),
        ]
    )

    assert result == 0
    out = capsys.readouterr().out
    assert "COMMENT:I might be 10 minutes late" in out
    assert "Status: TENTATIVE" in out


def test_reply_to_recurring_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test replying to a recurring event."""
    invite = _write_invite(
        tmp_path,
        EmailInvite(
            uid="recurring-reply@example.com",
            summary="Weekly Standup",
            to="dev@example.com",
            organizer="mailto:scrum@example.com",
            dtstart="20240320T090000Z",
            dtend="20240320T100000Z",
            extra="RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR",
        ),
    )

    result = main(["reply", "accept", "--dry-run", str(invite)])
    assert result == 0

    out = capsys.readouterr().out
    assert "Status: ACCEPTED" in out


def test_reply_missing_organizer(tmp_path: Path) -> None:
    """Test reply fails when organizer is missing."""
    invite_content = """\
From: sender@example.com
To: attendee@example.com
Subject: Meeting Invitation
Content-Type: text/calendar

BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:no-organizer@example.com
DTSTART:20240320T140000Z
DTEND:20240320T150000Z
SUMMARY:No Organizer Meeting
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:attendee@example.com
END:VEVENT
END:VCALENDAR"""

    invite = tmp_path / "no-org.ics"
    invite.write_text(invite_content)

    result = main(["reply", "accept", str(invite)])
    assert result == 1


def test_reply_invalid_ics_file(tmp_path: Path) -> None:
    """Test reply fails on invalid ics."""
    (tmp_path / "invalid.ics").write_text("This is not a valid ICS file")
    result = main(["reply", "accept", str(tmp_path / "invalid.ics")])
    assert result == 1


def test_reply_missing_to_header(tmp_path: Path) -> None:
    """Test reply fails when To header is missing (can't determine attendee email)."""
    invite_content = """\
From: sender@example.com
Subject: Meeting Invitation
Content-Type: text/calendar

BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:no-to-header@example.com
DTSTART:20240320T140000Z
DTEND:20240320T150000Z
SUMMARY:No To Header Meeting
ORGANIZER:mailto:organizer@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:attendee@example.com
END:VEVENT
END:VCALENDAR"""

    invite = tmp_path / "no-to.ics"
    invite.write_text(invite_content)

    result = main(["reply", "accept", str(invite)])
    assert result == 1


@patch("calendar_cli.reply.subprocess.run")
def test_reply_msmtp_failure(mock_run: MagicMock, tmp_path: Path) -> None:
    """Test msmtp failure returns error but still builds valid email."""
    mock_run.return_value = MagicMock(
        returncode=1, stdout="", stderr="msmtp: connection failed"
    )

    invite = _write_invite(
        tmp_path,
        EmailInvite(
            uid="msmtp-fail@example.com",
            to="testuser@example.com",
            summary="MSMTP Fail Test",
        ),
    )

    result = main(["reply", "accept", str(invite)])
    assert result == 1

    raw = mock_run.call_args[1]["input"]
    msg, cal = parse_reply_email(raw)

    _, to_addr = email.utils.parseaddr(msg["To"])
    assert to_addr == "organizer@example.com"
    assert str(cal["METHOD"]) == "REPLY"
    event = next(iter(cal.walk("VEVENT")))
    assert str(event["UID"]) == "msmtp-fail@example.com"


def test_reply_from_email_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test replying to calendar invite embedded in multipart email."""
    email_content = """\
From: sender@example.com
To: recipient@example.com
Subject: Meeting Invitation
Content-Type: multipart/mixed; boundary="boundary"

--boundary
Content-Type: text/plain

You're invited to a meeting.

--boundary
Content-Type: text/calendar; charset=utf-8
Content-Transfer-Encoding: 7bit

BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:email-embedded@example.com
DTSTART:20240320T140000Z
DTEND:20240320T150000Z
SUMMARY:Email Embedded Meeting
ORGANIZER:mailto:organizer@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:recipient@example.com
END:VEVENT
END:VCALENDAR
--boundary--"""

    (tmp_path / "meeting.eml").write_text(email_content)

    result = main(["reply", "accept", "--dry-run", str(tmp_path / "meeting.eml")])
    assert result == 0

    out = capsys.readouterr().out
    assert "Would send reply to: organizer@example.com" in out
    assert "Status: ACCEPTED" in out


def test_reply_always_has_dtstamp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reply VEVENT always has DTSTAMP even if original lacks it (RFC 5545 §3.6.1)."""
    invite = _write_invite(
        tmp_path,
        EmailInvite(
            uid="no-dtstamp@example.com",
            summary="No DTSTAMP Meeting",
        ),
    )

    result = main(["reply", "accept", "--dry-run", str(invite)])
    assert result == 0
    out = capsys.readouterr().out
    assert "DTSTAMP" in out


def test_reply_copies_recurrence_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reply copies RECURRENCE-ID to target the right instance (RFC 6047 §3.2.3)."""
    invite = _write_invite(
        tmp_path,
        EmailInvite(
            uid="recurrence-reply@example.com",
            summary="Rescheduled Instance",
            dtstart="20240327T140000Z",
            dtend="20240327T150000Z",
            extra="RECURRENCE-ID:20240327T140000Z",
        ),
    )

    result = main(["reply", "accept", "--dry-run", str(invite)])
    assert result == 0
    out = capsys.readouterr().out
    assert "RECURRENCE-ID" in out


def test_reply_has_calscale(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Reply calendar includes CALSCALE:GREGORIAN."""
    invite = _write_invite(
        tmp_path,
        EmailInvite(uid="calscale@example.com"),
    )
    result = main(["reply", "accept", "--dry-run", str(invite)])
    assert result == 0
    out = capsys.readouterr().out
    assert "CALSCALE:GREGORIAN" in out


def test_reply_from_stdin(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test replying from stdin."""
    invite = make_email_invite(
        EmailInvite(
            uid="stdin-reply@example.com",
            summary="Stdin Reply Test",
        )
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(invite))

    result = main(["reply", "decline", "--dry-run"])
    assert result == 0

    out = capsys.readouterr().out
    assert "Status: DECLINED" in out


def test_reply_matches_uppercase_mailto(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """MAILTO: (uppercase) in ATTENDEE should be matched when creating a reply."""
    invite_ics = """\
From: sender@example.com
To: attendee@example.com
Subject: Meeting
Content-Type: text/calendar

BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
BEGIN:VEVENT
UID:uppercase-mailto@example.com
DTSTART:20240320T140000Z
DTEND:20240320T150000Z
SUMMARY:Uppercase MAILTO Test
ORGANIZER:MAILTO:organizer@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:MAILTO:attendee@example.com
END:VEVENT
END:VCALENDAR"""

    invite_file = tmp_path / "invite.eml"
    invite_file.write_text(invite_ics)

    result = main(["reply", "accept", "--dry-run", str(invite_file)])
    assert result == 0

    out = capsys.readouterr().out
    assert "ACCEPTED" in out
    # The reply should target the organizer
    assert "organizer@example.com" in out


@patch("calendar_cli.reply.subprocess.run")
def test_reply_updates_local_partstat(mock_run: MagicMock, tmp_path: Path) -> None:
    """After sending a reply, our PARTSTAT in the local store should be updated."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    cal_dir = tmp_path / "calendars"

    # First import the invite into the local store
    invite_ics = make_ics(
        ICSEvent(
            uid="local-update@example.com",
            summary="Local Update Test",
            vcalendar_lines=["METHOD:REQUEST"],
            vevent_lines=[
                "ORGANIZER:mailto:organizer@example.com",
                "ATTENDEE;CN=Me;PARTSTAT=NEEDS-ACTION:mailto:me@example.com",
            ],
        )
    )
    import_to_local(invite_ics.encode(), "personal", str(cal_dir))

    # Write the email invite file (reply reads from this)
    invite_email = make_email_invite(
        EmailInvite(
            uid="local-update@example.com",
            to="me@example.com",
            summary="Local Update Test",
            organizer="mailto:organizer@example.com",
        )
    )
    email_file = tmp_path / "invite.eml"
    email_file.write_text(invite_email)

    # Send accept reply — this should update the local store too
    result = main(
        [
            "--calendar-dir",
            str(cal_dir),
            "--no-sync",
            "reply",
            "accept",
            str(email_file),
        ]
    )
    assert result == 0

    # Verify local store was updated
    ics_files = sorted((cal_dir / "personal").rglob("*.ics"))
    assert len(ics_files) == 1
    cal = Calendar.from_ical(ics_files[0].read_bytes())
    event = next(iter(cal.walk("VEVENT")))
    attendee = event.get("attendee")
    # Single attendee comes back as vCalAddress, not list
    att = attendee[0] if isinstance(attendee, list) else attendee
    assert att.params["PARTSTAT"] == "ACCEPTED"
