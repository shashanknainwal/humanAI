"""Book the follow-up call as a calendar invite (.ics) any calendar app can import."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _ics_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


def build_invite(
    title: str,
    start: datetime,
    *,
    duration_minutes: int = 15,
    meeting_url: str | None = None,
    description: str = "",
) -> str:
    end = start + timedelta(minutes=duration_minutes)
    desc = description + (f"\n\nJoin: {meeting_url}" if meeting_url else "")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//teammate//follow-up//EN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@teammate",
        f"DTSTAMP:{_ics_time(datetime.now(UTC))}",
        f"DTSTART:{_ics_time(start)}",
        f"DTEND:{_ics_time(end)}",
        f"SUMMARY:{_escape(title)}",
        f"DESCRIPTION:{_escape(desc.strip())}",
    ]
    if meeting_url:
        lines.append(f"LOCATION:{_escape(meeting_url)}")
    lines += ["END:VEVENT", "END:VCALENDAR", ""]
    return "\r\n".join(lines)


def book_followup(
    path: Path,
    task_title: str,
    eta_minutes: int,
    *,
    meeting_url: str | None = None,
    now: datetime | None = None,
) -> datetime:
    """Write the invite and return when the follow-up starts."""
    now = now or datetime.now(UTC)
    # Small buffer so the report is written before the call starts.
    start = now + timedelta(minutes=eta_minutes + 5)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_invite(
            f"Follow-up: {task_title}",
            start,
            meeting_url=meeting_url,
            description=f"Your AI teammate reports back on: {task_title}",
        )
    )
    return start
