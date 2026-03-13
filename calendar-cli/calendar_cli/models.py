"""Data models for calendar events and attendees."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _format_trigger(td: timedelta) -> str:
    """Format an alarm trigger timedelta as a human-readable string.

    Alarm triggers are negative timedeltas (e.g. -15 minutes = timedelta(-1, 85500)).
    Convert to a positive "Xm/Xh/Xd before" string that LLMs can understand.
    """
    total_seconds = int(abs(td.total_seconds()))
    if total_seconds == 0:
        return "at event time"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m before"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        if remaining_minutes:
            return f"{hours}h{remaining_minutes}m before"
        return f"{hours}h before"
    days = hours // 24
    remaining_hours = hours % 24
    if remaining_hours:
        return f"{days}d{remaining_hours}h before"
    return f"{days}d before"


@dataclass
class Attendee:
    """An event attendee with RSVP status."""

    email: str
    name: str = ""
    status: str = "NEEDS-ACTION"  # ACCEPTED, DECLINED, TENTATIVE, NEEDS-ACTION

    def __str__(self) -> str:
        label = self.name or self.email
        if self.status and self.status != "NEEDS-ACTION":
            return f"{label} ({self.status.lower()})"
        return label


@dataclass
class CalendarEvent:
    """Parsed representation of a VEVENT for display."""

    uid: str
    summary: str
    dtstart: datetime | date
    dtend: datetime | date | None
    location: str
    description: str
    calendar: str
    rrule: str
    filepath: Path
    alarm_minutes: list[int] = field(default_factory=list)
    url: str = ""
    organizer: str = ""
    attendees: list[Attendee] = field(default_factory=list)
    status: str = ""  # CONFIRMED, TENTATIVE, CANCELLED
    recurrence_id: datetime | date | None = None
    exdates: list[datetime | date] = field(default_factory=list)
    rdates: list[datetime | date] = field(default_factory=list)

    @property
    def alarms(self) -> list[str]:
        """Human-readable alarm descriptions."""
        return [_format_trigger(timedelta(minutes=-m)) for m in self.alarm_minutes]

    @property
    def is_all_day(self) -> bool:
        return isinstance(self.dtstart, date) and not isinstance(self.dtstart, datetime)

    def start_dt(self) -> datetime:
        """Return dtstart as a timezone-aware datetime."""
        if isinstance(self.dtstart, datetime):
            if self.dtstart.tzinfo is None:
                return self.dtstart.replace(tzinfo=UTC)
            return self.dtstart
        return datetime.combine(self.dtstart, datetime.min.time(), tzinfo=UTC)
