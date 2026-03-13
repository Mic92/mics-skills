"""Shared pytest fixtures for calendar-cli tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .helpers import ICSEvent, make_ics, setup_calendar_dir

if TYPE_CHECKING:
    from pathlib import Path

_WEEKLY_STANDUP_ICS = (
    "BEGIN:VCALENDAR\n"
    "VERSION:2.0\n"
    "PRODID:-//test//test//\n"
    "BEGIN:VEVENT\n"
    "UID:event3-uid\n"
    "SUMMARY:Weekly standup\n"
    "DTSTART;TZID=Europe/Berlin:20250401T090000\n"
    "DTEND;TZID=Europe/Berlin:20250401T091500\n"
    "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10\n"
    "BEGIN:VALARM\n"
    "TRIGGER:-PT15M\n"
    "ACTION:DISPLAY\n"
    "DESCRIPTION:Standup reminder\n"
    "END:VALARM\n"
    "END:VEVENT\n"
    "END:VCALENDAR\n"
)


@pytest.fixture
def cal_dir(tmp_path: Path) -> str:
    """Create a temporary calendar directory with sample events.

    Contains two calendars (``personal`` with 3 events, ``work`` with 1).
    Used by both test_cli.py and test_store.py.
    """
    return setup_calendar_dir(
        tmp_path,
        {
            "personal": {
                "event1.ics": make_ics(
                    ICSEvent(
                        uid="event1-uid",
                        summary="Dentist appointment",
                        dtstart="20250401T100000Z",
                        dtend="20250401T110000Z",
                        vevent_lines=[
                            "LOCATION:Dr. Smith",
                            "DESCRIPTION:Annual checkup",
                        ],
                    ),
                ),
                "event2.ics": make_ics(
                    ICSEvent(
                        uid="event2-uid",
                        summary="Company Holiday",
                        dtstart=";VALUE=DATE:20250401",
                        dtend=";VALUE=DATE:20250402",
                    ),
                ),
                "event3.ics": _WEEKLY_STANDUP_ICS,
            },
            "work": {
                "event4.ics": make_ics(
                    ICSEvent(
                        uid="event4-uid",
                        summary="Sprint planning",
                        dtstart="20250402T140000Z",
                        dtend="20250402T150000Z",
                    ),
                ),
            },
        },
    )
