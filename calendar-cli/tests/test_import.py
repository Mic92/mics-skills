"""Tests for the calendar-cli import command."""

from hashlib import sha1
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from calendar_cli.import_invite import (
    _calendar_has_rsvp,
    extract_calendar_from_email,
    import_to_local,
)
from calendar_cli.main import main
from icalendar import Calendar

from .helpers import ICSEvent, make_ics

BASIC_ICS = make_ics(
    ICSEvent(
        uid="test-uid@example.com",
        summary="Test Meeting",
        dtstart="20240320T140000Z",
        dtend="20240320T150000Z",
    )
)


def _find_imported_ics(base: Path) -> list[Path]:
    return sorted(base.rglob("*.ics"))


def _parse_imported(path: Path) -> Calendar:
    cal = Calendar.from_ical(path.read_text())
    assert isinstance(cal, Calendar)
    return cal


def test_import_basic_ics(tmp_path: Path) -> None:
    """Test importing a .ics file writes a parseable event to the store."""
    cal_dir = tmp_path / "calendars"
    result = import_to_local(BASIC_ICS.encode(), "personal", str(cal_dir))

    assert result is True

    files = _find_imported_ics(cal_dir)
    assert len(files) == 1
    assert "test-uid@example.com" in files[0].name

    cal = _parse_imported(files[0])
    event = next(iter(cal.walk("VEVENT")))
    assert str(event["UID"]) == "test-uid@example.com"
    assert str(event["SUMMARY"]) == "Test Meeting"


@patch("calendar_cli.import_invite.subprocess.run")
def test_import_from_email(mock_run: MagicMock, tmp_path: Path) -> None:
    """Test importing calendar invite from multipart email."""
    mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

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
UID:email-invite@example.com
DTSTART:20240320T140000Z
DTEND:20240320T150000Z
SUMMARY:Email Meeting
ORGANIZER:mailto:organizer@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:attendee@example.com
END:VEVENT
END:VCALENDAR
--boundary--"""

    email_file = tmp_path / "email.eml"
    email_file.write_text(email_content)

    cal_dir = str(tmp_path / "calendars")
    result = main(["--calendar-dir", cal_dir, "--no-sync", "import", str(email_file)])
    assert result == 0


def test_import_invalid_ics(tmp_path: Path) -> None:
    """Test importing invalid ICS file fails."""
    (tmp_path / "invalid.ics").write_text("This is not a valid ICS file")
    result = main(["--no-sync", "import", str(tmp_path / "invalid.ics")])
    assert result == 1


def test_import_nonexistent_file() -> None:
    """Test importing non-existent file fails."""
    result = main(["--no-sync", "import", "/non/existent/file.ics"])
    assert result == 1


def test_import_groups_by_uid(tmp_path: Path) -> None:
    """Import with multiple VEVENTs sharing a UID writes one file."""
    override_vevent = (
        "BEGIN:VEVENT\n"
        "UID:recurring@example.com\n"
        "RECURRENCE-ID:20240327T140000Z\n"
        "DTSTART:20240327T150000Z\n"
        "DTEND:20240327T160000Z\n"
        "SUMMARY:Weekly Meeting (rescheduled)\n"
        "END:VEVENT"
    )
    ics = make_ics(
        ICSEvent(
            uid="recurring@example.com",
            summary="Weekly Meeting",
            dtstart="20240320T140000Z",
            dtend="20240320T150000Z",
            vevent_lines=["RRULE:FREQ=WEEKLY;COUNT=3"],
            extra_components=override_vevent,
        )
    )

    cal_dir = tmp_path / "calendars"
    result = import_to_local(ics.encode(), "personal", str(cal_dir))
    assert result is True

    files = sorted((cal_dir / "personal").rglob("*.ics"))
    assert len(files) == 1  # One file for the UID, not two

    cal = _parse_imported(files[0])
    events = list(cal.walk("VEVENT"))
    assert len(events) == 2  # Both VEVENTs in the same file


def test_import_unsafe_uid(tmp_path: Path) -> None:
    """UIDs with filesystem-unsafe characters get hashed filenames."""
    uid = "uid with spaces/and:colons"
    ics = make_ics(ICSEvent(uid=uid, summary="Unsafe UID Test"))

    cal_dir = tmp_path / "calendars"
    result = import_to_local(ics.encode(), "personal", str(cal_dir))
    assert result is True

    files = sorted((cal_dir / "personal").rglob("*.ics"))
    assert len(files) == 1
    expected_name = sha1(uid.encode(), usedforsecurity=False).hexdigest() + ".ics"
    assert files[0].name == expected_name

    cal = _parse_imported(files[0])
    event = next(iter(cal.walk("VEVENT")))
    assert str(event["UID"]) == uid  # UID preserved inside the file


def test_import_windows_timezone(tmp_path: Path) -> None:
    """Outlook-style Windows timezone names are normalized during import."""
    ics = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VTIMEZONE
TZID:Eastern Standard Time
BEGIN:STANDARD
DTSTART:16011104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:outlook-tz@example.com
DTSTART;TZID=Eastern Standard Time:20240320T140000
DTEND;TZID=Eastern Standard Time:20240320T150000
SUMMARY:Outlook Meeting
END:VEVENT
END:VCALENDAR"""

    cal_dir = tmp_path / "calendars"
    result = import_to_local(ics.encode(), "personal", str(cal_dir))
    assert result is True

    files = _find_imported_ics(cal_dir / "personal")
    assert len(files) == 1

    cal = _parse_imported(files[0])
    # The VTIMEZONE should be included in the output
    tzs = [c for c in cal.walk() if c.name == "VTIMEZONE"]
    assert len(tzs) == 1


def test_import_missing_uid(tmp_path: Path) -> None:
    """Events without UID get a generated one."""
    ics = make_ics(ICSEvent(uid="", summary="No UID Event"))
    # Remove the UID line entirely to simulate a truly missing UID
    ics = "\n".join(line for line in ics.splitlines() if not line.startswith("UID:"))

    cal_dir = tmp_path / "calendars"
    result = import_to_local(ics.encode(), "personal", str(cal_dir))
    assert result is True

    files = _find_imported_ics(cal_dir / "personal")
    assert len(files) == 1

    cal = _parse_imported(files[0])
    event = next(iter(cal.walk("VEVENT")))
    assert event.get("UID") is not None


def test_import_calscale_in_output(tmp_path: Path) -> None:
    """Imported events include CALSCALE:GREGORIAN."""
    cal_dir = tmp_path / "calendars"
    import_to_local(BASIC_ICS.encode(), "personal", str(cal_dir))
    files = _find_imported_ics(cal_dir)
    assert len(files) == 1
    raw = files[0].read_bytes().decode()
    assert "CALSCALE:GREGORIAN" in raw


def test_rsvp_detection_uses_parsed_params(tmp_path: Path) -> None:
    """RSVP detection works via iCalendar parameter parsing, not byte search."""
    ics_with_rsvp = make_ics(
        ICSEvent(
            uid="rsvp-test@example.com",
            summary="RSVP Test",
            vevent_lines=["ATTENDEE;RSVP=TRUE:mailto:test@example.com"],
        )
    ).encode()

    ics_without_rsvp = make_ics(
        ICSEvent(
            uid="no-rsvp@example.com",
            summary="No RSVP",
            vevent_lines=[
                "DESCRIPTION:This text mentions RSVP=TRUE but is not an attendee param"
            ],
        )
    ).encode()

    assert _calendar_has_rsvp(ics_with_rsvp) is True
    assert _calendar_has_rsvp(ics_without_rsvp) is False


@patch("calendar_cli.import_invite.sys.stdin")
def test_import_from_stdin(
    mock_stdin: MagicMock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test importing from stdin."""
    mock_stdin.buffer.read.return_value = BASIC_ICS.encode()

    cal_dir = str(tmp_path / "calendars")
    with patch("calendar_cli.import_invite.subprocess.run"):
        result = main(["--calendar-dir", cal_dir, "--no-sync", "import"])

    assert result == 0
    captured = capsys.readouterr()
    assert "Successfully imported 1 calendar invite(s)" in captured.out


# ---------------------------------------------------------------------------
# Issue #13: METHOD:CANCEL and METHOD:REPLY handling
# ---------------------------------------------------------------------------


def test_import_method_cancel_deletes_event(tmp_path: Path) -> None:
    """METHOD:CANCEL should delete the matching local event."""
    cal_dir = tmp_path / "calendars"

    # First, import a normal event
    import_to_local(BASIC_ICS.encode(), "personal", str(cal_dir))
    files_before = _find_imported_ics(cal_dir / "personal")
    assert len(files_before) == 1

    # Now import a cancellation for the same UID
    cancel_ics = make_ics(
        ICSEvent(
            uid="test-uid@example.com",
            summary="Test Meeting",
            vcalendar_lines=["METHOD:CANCEL"],
            vevent_lines=["STATUS:CANCELLED", "SEQUENCE:1"],
        )
    )

    result = import_to_local(cancel_ics.encode(), "personal", str(cal_dir))
    assert result is True

    # The original file should be gone
    files_after = _find_imported_ics(cal_dir / "personal")
    assert len(files_after) == 0


def test_import_method_reply_updates_partstat(tmp_path: Path) -> None:
    """METHOD:REPLY should update the attendee's PARTSTAT in the local event."""
    cal_dir = tmp_path / "calendars"

    # Import an event with attendees
    invite_ics = make_ics(
        ICSEvent(
            uid="reply-test@example.com",
            summary="Reply Test",
            vcalendar_lines=["METHOD:REQUEST"],
            vevent_lines=[
                "ORGANIZER:mailto:alice@example.com",
                "ATTENDEE;CN=Bob;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com",
            ],
        )
    )

    import_to_local(invite_ics.encode(), "personal", str(cal_dir))

    # Verify initial state
    files = _find_imported_ics(cal_dir / "personal")
    assert len(files) == 1
    cal = _parse_imported(files[0])
    event = next(iter(cal.walk("VEVENT")))
    attendee = event.get("attendee")
    assert attendee.params["PARTSTAT"] == "NEEDS-ACTION"

    # Now import Bob's REPLY accepting the invite
    reply_ics = make_ics(
        ICSEvent(
            uid="reply-test@example.com",
            summary="Reply Test",
            vcalendar_lines=["METHOD:REPLY"],
            vevent_lines=[
                "ATTENDEE;CN=Bob;PARTSTAT=ACCEPTED:mailto:bob@example.com",
            ],
        )
    )

    result = import_to_local(reply_ics.encode(), "personal", str(cal_dir))
    assert result is True

    # Verify PARTSTAT was updated
    cal = _parse_imported(files[0])
    event = next(iter(cal.walk("VEVENT")))
    attendee = event.get("attendee")
    assert attendee.params["PARTSTAT"] == "ACCEPTED"


def test_import_method_cancel_unknown_uid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """METHOD:CANCEL for an unknown UID should warn, not crash."""
    cal_dir = tmp_path / "calendars"
    (cal_dir / "personal").mkdir(parents=True)

    cancel_ics = make_ics(
        ICSEvent(
            uid="nonexistent@example.com",
            summary="Ghost Event",
            vcalendar_lines=["METHOD:CANCEL"],
            vevent_lines=["STATUS:CANCELLED", "SEQUENCE:1"],
        )
    )

    result = import_to_local(cancel_ics.encode(), "personal", str(cal_dir))
    assert result is False
    err = capsys.readouterr().err
    assert "unknown event" in err.lower() or "nonexistent" in err.lower()


def test_import_method_reply_decline(tmp_path: Path) -> None:
    """METHOD:REPLY with DECLINED updates the attendee status."""
    cal_dir = tmp_path / "calendars"

    invite_ics = make_ics(
        ICSEvent(
            uid="decline-test@example.com",
            summary="Decline Test",
            vcalendar_lines=["METHOD:REQUEST"],
            vevent_lines=[
                "ORGANIZER:mailto:alice@example.com",
                "ATTENDEE;CN=Bob;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com",
            ],
        )
    )
    import_to_local(invite_ics.encode(), "personal", str(cal_dir))

    reply_ics = make_ics(
        ICSEvent(
            uid="decline-test@example.com",
            summary="Decline Test",
            vcalendar_lines=["METHOD:REPLY"],
            vevent_lines=[
                "ATTENDEE;CN=Bob;PARTSTAT=DECLINED:mailto:bob@example.com",
            ],
        )
    )
    result = import_to_local(reply_ics.encode(), "personal", str(cal_dir))
    assert result is True

    files = _find_imported_ics(cal_dir / "personal")
    cal = _parse_imported(files[0])
    event = next(iter(cal.walk("VEVENT")))
    attendee = event.get("attendee")
    assert attendee.params["PARTSTAT"] == "DECLINED"


def test_import_method_reply_multiple_attendees(tmp_path: Path) -> None:
    """REPLY from one attendee should not change another attendee's status."""
    cal_dir = tmp_path / "calendars"

    invite_ics = make_ics(
        ICSEvent(
            uid="multi-att@example.com",
            summary="Multi Attendee",
            vcalendar_lines=["METHOD:REQUEST"],
            vevent_lines=[
                "ORGANIZER:mailto:alice@example.com",
                "ATTENDEE;CN=Bob;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com",
                "ATTENDEE;CN=Carol;PARTSTAT=NEEDS-ACTION:mailto:carol@example.com",
            ],
        )
    )
    import_to_local(invite_ics.encode(), "personal", str(cal_dir))

    # Bob accepts
    reply_ics = make_ics(
        ICSEvent(
            uid="multi-att@example.com",
            summary="Multi Attendee",
            vcalendar_lines=["METHOD:REPLY"],
            vevent_lines=[
                "ATTENDEE;CN=Bob;PARTSTAT=ACCEPTED:mailto:bob@example.com",
            ],
        )
    )
    import_to_local(reply_ics.encode(), "personal", str(cal_dir))

    files = _find_imported_ics(cal_dir / "personal")
    cal = _parse_imported(files[0])
    event = next(iter(cal.walk("VEVENT")))
    attendees = event.get("attendee")
    assert isinstance(attendees, list)

    by_email = {
        str(a).replace("mailto:", "").replace("MAILTO:", ""): a for a in attendees
    }
    assert by_email["bob@example.com"].params["PARTSTAT"] == "ACCEPTED"
    assert by_email["carol@example.com"].params["PARTSTAT"] == "NEEDS-ACTION"


def test_import_method_reply_unknown_uid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """REPLY for an unknown UID should warn and return False."""
    cal_dir = tmp_path / "calendars"
    (cal_dir / "personal").mkdir(parents=True)

    reply_ics = make_ics(
        ICSEvent(
            uid="ghost@example.com",
            summary="Ghost Reply",
            vcalendar_lines=["METHOD:REPLY"],
            vevent_lines=[
                "ATTENDEE;CN=Bob;PARTSTAT=ACCEPTED:mailto:bob@example.com",
            ],
        )
    )
    result = import_to_local(reply_ics.encode(), "personal", str(cal_dir))
    assert result is False
    err = capsys.readouterr().err
    assert "unknown event" in err.lower() or "ghost" in err.lower()


def test_import_cancel_across_calendars(tmp_path: Path) -> None:
    """CANCEL finds and removes the event even if it's in a different calendar."""
    cal_dir = tmp_path / "calendars"

    # Import into "work" calendar
    import_to_local(BASIC_ICS.encode(), "work", str(cal_dir))
    assert len(_find_imported_ics(cal_dir / "work")) == 1

    # Cancel without specifying calendar — should find it in "work"
    cancel_ics = make_ics(
        ICSEvent(
            uid="test-uid@example.com",
            summary="Test Meeting",
            vcalendar_lines=["METHOD:CANCEL"],
            vevent_lines=["STATUS:CANCELLED"],
        )
    )
    result = import_to_local(cancel_ics.encode(), "personal", str(cal_dir))
    assert result is True
    assert len(_find_imported_ics(cal_dir / "work")) == 0


def test_extract_calendar_no_duplicates() -> None:
    """A MIME part matching both content-type and filename should be extracted once."""
    email_content = b"""\
From: sender@example.com
To: recipient@example.com
Subject: Meeting
Content-Type: multipart/mixed; boundary="boundary"

--boundary
Content-Type: text/calendar; charset=utf-8
Content-Disposition: attachment; filename="invite.ics"

BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:dup-test@example.com
DTSTART:20240320T140000Z
DTEND:20240320T150000Z
SUMMARY:Duplicate Test
END:VEVENT
END:VCALENDAR
--boundary--"""

    cals = extract_calendar_from_email(email_content)
    assert len(cals) == 1
