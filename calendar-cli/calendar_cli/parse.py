"""Parse VEVENT components from icalendar objects into CalendarEvent models."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from icalendar import Calendar, Component

if TYPE_CHECKING:
    from pathlib import Path

from .models import Attendee, CalendarEvent
from .timeutil import coerce_to_datetime, sanitize_timerange
from .util import get_attendee_list, strip_mailto

log = logging.getLogger(__name__)


def _parse_rrule(event: Component) -> str:
    rrule = event.get("rrule")
    if rrule is None:
        return ""
    result: str = rrule.to_ical().decode()
    return result


def _parse_alarm_minutes(event: Component) -> list[int]:
    """Extract alarm triggers as positive minutes-before values.

    Handles three trigger forms per RFC 5545 §3.8.6.3:
    - Duration relative to DTSTART (default): e.g. -PT15M
    - Duration relative to DTEND (RELATED=END): e.g. -PT5M
    - Absolute datetime: e.g. 20250401T120000Z — converted to a
      duration relative to the reference point so it fits our
      minutes model.

    When the trigger's RELATED parameter is END, DTEND is used as the
    reference; otherwise DTSTART (the default per RFC 5545).

    Note: our data model stores a flat list of minute values and cannot
    distinguish "before start" from "before end".  The stored value
    represents how many minutes before the *reference point* the alarm
    fires.
    """
    dtstart = _dt_value(event.get("dtstart"))
    dtend = _dt_value(event.get("dtend"))
    minutes: list[int] = []
    for component in event.subcomponents:
        if component.name == "VALARM":
            trigger = component.get("trigger")
            if trigger is None:
                continue
            related = trigger.params.get("RELATED", "START").upper()
            ref = dtend if related == "END" and dtend is not None else dtstart
            dt = trigger.dt
            if isinstance(dt, timedelta):
                minutes.append(int(abs(dt.total_seconds()) / 60))
            elif isinstance(dt, datetime) and ref is not None:
                # Absolute trigger — compute offset from reference
                ref_dt = coerce_to_datetime(ref)
                delta = ref_dt - dt
                minutes.append(max(0, int(delta.total_seconds() / 60)))
    return minutes


def _dt_value(val: object) -> datetime | date | None:
    """Extract a date or datetime from an icalendar property."""
    if val is None:
        return None
    # icalendar wraps values in vDate/vDatetime with a .dt attribute
    dt = getattr(val, "dt", val)
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, date):
        return dt
    return None


def _parse_organizer(component: Component) -> str:
    """Extract organizer as 'Name (email)' or just email."""
    org = component.get("organizer")
    if org is None:
        return ""
    cn = org.params.get("CN", "")
    addr = strip_mailto(str(org))
    if cn:
        return f"{cn} ({addr})"
    return addr


def _parse_date_list(component: Component, prop_name: str) -> list[datetime | date]:
    """Extract a list of date/datetime values from a multi-value property.

    Works for both EXDATE and RDATE which share the same vDDDLists
    structure — either a single vDDDLists or a list of them.
    """
    result: list[datetime | date] = []
    raw = component.get(prop_name)
    if raw is None:
        return result
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        for dt_val in item.dts:
            dt = dt_val.dt
            if isinstance(dt, (datetime, date)):
                result.append(dt)
    return result


def _parse_exdates(component: Component) -> list[datetime | date]:
    """Extract EXDATE values from a VEVENT component."""
    return _parse_date_list(component, "exdate")


def _parse_rdates(component: Component) -> list[datetime | date]:
    """Extract RDATE values from a VEVENT component (RFC 5545 §3.8.5.2)."""
    return _parse_date_list(component, "rdate")


def _parse_attendees(component: Component) -> list[Attendee]:
    """Extract attendees with name, email, and PARTSTAT."""
    attendees: list[Attendee] = []
    for addr in get_attendee_list(component):
        email_addr = strip_mailto(str(addr))
        name = addr.params.get("CN", "")
        status = addr.params.get("PARTSTAT", "NEEDS-ACTION")
        attendees.append(Attendee(email=email_addr, name=str(name), status=str(status)))
    return attendees


def read_event_file(path: Path, calendar_name: str) -> list[CalendarEvent]:
    """Parse a single .ics file and return CalendarEvent(s)."""
    events: list[CalendarEvent] = []
    try:
        data = path.read_text()
        cal = Calendar.from_ical(data)
    except (ValueError, OSError):
        return events

    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        uid = str(component.get("uid", path.stem))
        summary = str(component.get("summary", "(no title)"))
        dtstart = _dt_value(component.get("dtstart"))
        if dtstart is None:
            continue
        raw_dtend = _dt_value(component.get("dtend"))
        duration_prop = component.get("duration")
        duration = duration_prop.dt if duration_prop is not None else None
        dtstart, dtend = sanitize_timerange(dtstart, raw_dtend, duration)
        location = str(component.get("location", ""))
        description = str(component.get("description", ""))
        rrule = _parse_rrule(component)
        alarms = _parse_alarm_minutes(component)
        url = str(component.get("url", ""))
        organizer = _parse_organizer(component)
        attendees = _parse_attendees(component)
        status = str(component.get("status", ""))
        recurrence_id = _dt_value(component.get("recurrence-id"))
        exdates = _parse_exdates(component)
        rdates = _parse_rdates(component)
        events.append(
            CalendarEvent(
                uid=uid,
                summary=summary,
                dtstart=dtstart,
                dtend=dtend,
                location=location,
                description=description,
                calendar=calendar_name,
                rrule=rrule,
                filepath=path,
                alarm_minutes=alarms,
                url=url,
                organizer=organizer,
                attendees=attendees,
                status=status,
                recurrence_id=recurrence_id,
                exdates=exdates,
                rdates=rdates,
            )
        )
    return events
