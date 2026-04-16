from string import Template

from datetime import datetime, timedelta, timezone

SESSION_MESSAGE = Template("""
$party_tag Do we play at <t:$ts:f>?
"""
)

def get_next_session_timestamp() -> int:
    now = datetime.now(timezone.utc)
    target = (now + timedelta(days=(5 - now.weekday()) % 7)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    if target <= now:
        target += timedelta(days=7)

    return int(target.timestamp())

def get_session_message(party_tag: str) -> str:
    return SESSION_MESSAGE.substitute(
        party_tag=party_tag,
        ts=get_next_session_timestamp(),
    )
