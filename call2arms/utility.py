import datetime
from call2arms.config import VoteWeekParity


def get_week_parity(
    now: datetime.datetime | None = None,
) -> VoteWeekParity:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    iso_week = now.isocalendar().week
    return VoteWeekParity.even if iso_week % 2 == 0 else VoteWeekParity.odd


def check_schedule(target_parity: VoteWeekParity) -> bool:
    now = datetime.datetime.now(datetime.timezone.utc)

    if now.weekday() != 1:
        return False

    return get_week_parity(now) == target_parity
