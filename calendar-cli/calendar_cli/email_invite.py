"""Build and send calendar invite emails via msmtp."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from .errors import SendError

if TYPE_CHECKING:
    from datetime import datetime

    from icalendar import Calendar

    from .create import MeetingConfig


def _format_time_with_tz(dt: datetime) -> str:
    """Format a time as ``HH:MM AM/PM TZ``, with a safe timezone suffix.

    ``strftime("%Z")`` returns an empty string for naive datetimes, which
    would leave a stray trailing space.  This helper uses the tzname when
    available and falls back to the numeric UTC offset (``%z``) or omits
    the suffix entirely for naive datetimes.
    """
    time_part = dt.strftime("%I:%M %p")
    if dt.tzinfo is not None:
        tz_label = dt.tzname() or dt.strftime("%z")
        if tz_label:
            return f"{time_part} {tz_label}"
    return time_part


@dataclass
class EmailConfig:
    """Configuration for sending email."""

    cal: Calendar
    config: MeetingConfig
    dry_run: bool = False


def _sanitize_header(value: str) -> str:
    """Strip CR/LF and other control characters that could cause header injection."""
    return value.translate(str.maketrans("", "", "\r\n\x00"))


def build_invite_email(email_config: EmailConfig) -> MIMEMultipart:
    """Build the MIME email message for a calendar invite."""
    summary = _sanitize_header(email_config.config.summary)
    org_name = _sanitize_header(email_config.config.organizer_name)
    org_email = _sanitize_header(email_config.config.organizer_email)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"Invitation: {summary}"
    msg["From"] = f"{org_name} <{org_email}>"

    # Build recipient list
    to_list = []
    for name, email_addr in email_config.config.attendees:
        clean_addr = _sanitize_header(email_addr)
        if name:
            to_list.append(f"{_sanitize_header(name)} <{clean_addr}>")
        else:
            to_list.append(clean_addr)

    msg["To"] = ", ".join(to_list)

    # Create email body
    start_time = _format_time_with_tz(email_config.config.start)
    end_time = _format_time_with_tz(email_config.config.end)
    body_text = f"""You have been invited to: {email_config.config.summary}

When: {email_config.config.start.strftime("%A, %B %d, %Y")}
Time: {start_time} - {end_time}"""

    if email_config.config.meeting_link:
        body_text += f"\n\nJoin meeting: {email_config.config.meeting_link}"

    body_text += "\n\nPlease see the attached calendar invitation for details."

    # Add text part
    msg.attach(MIMEText(body_text, "plain"))

    # Add calendar part
    cal_part = MIMEBase("text", "calendar")
    cal_part.set_payload(email_config.cal.to_ical())
    cal_part.add_header("Content-Disposition", 'attachment; filename="invite.ics"')
    cal_part.replace_header(
        "Content-Type",
        'text/calendar; charset="UTF-8"; method=REQUEST',
    )
    encoders.encode_base64(cal_part)
    msg.attach(cal_part)

    return msg


def send_invite_email(msg: MIMEMultipart) -> None:
    """Send a MIME email message via msmtp.

    Raises ``SendError`` on failure.
    """
    try:
        result = subprocess.run(
            ["msmtp", "-t"],
            input=msg.as_string(),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as e:
        err_msg = f"Failed to run msmtp: {e}"
        raise SendError(err_msg) from e
    if result.returncode != 0:
        err_msg = f"msmtp failed: {result.stderr.strip()}"
        raise SendError(err_msg)
