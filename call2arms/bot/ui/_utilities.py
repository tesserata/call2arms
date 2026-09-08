from datetime import UTC, datetime

from dateutil import parser as dateparser

from call2arms.model import Session


def parse_datetime(value: str) -> datetime:
    parsed = dateparser.parse(value)
    if parsed is None:
        raise ValueError(f"Could not parse {value!r} as a date/time")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def fmt_ts(dt: datetime, style: str = "f") -> str:
    return f"<t:{int(dt.timestamp())}:{style}>"


def session_line(session: Session) -> str:
    number = f"#{session.number}" if session.number is not None else "#?"
    status = "  ~~cancelled~~" if session.cancelled else ""
    return f"{session.campaign_name} session {number} — {fmt_ts(session.starts_at)}{status}"
