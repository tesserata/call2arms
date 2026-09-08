import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, time, timedelta
from functools import wraps
from pathlib import Path
from uuid import UUID

from call2arms.model import Campaign, Session


def mutation(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        result = await func(self, *args, **kwargs)
        self._mutated = True
        return result

    return wrapper


class DataStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.campaigns: dict[UUID, Campaign] = {}

        self._lock = asyncio.Lock()
        self._mutated: bool = False

    def load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                corrupted_bu = self.path.with_suffix(self.path.suffix + ".corrupt")
                self.path.replace(corrupted_bu)
                raise
            self.campaigns = {
                UUID(c["id"]): Campaign.from_dict(c) for c in raw.get("campaigns", [])
            }

    async def save(self, force: bool = False) -> None:
        if not self._mutated and not force:
            return
        snapshot = {
            "campaigns": [c.to_dict() for c in self.campaigns.values()],
        }
        async with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        self._mutated = False

    @mutation
    async def add_campaign(self, campaign: Campaign) -> None:
        self.campaigns[campaign.id] = campaign

    @mutation
    async def add_session(self, campaign_id: UUID, session: Session) -> None:
        campaign = self.campaigns[campaign_id]
        campaign.add_session(session)

    @mutation
    async def move_session(
        self, campaign_id: UUID, session_id: UUID, new_time: datetime
    ) -> None:
        campaign = self.campaigns[campaign_id]
        session = campaign.sessions[session_id]
        session.starts_at = new_time
        campaign.update_session(session)

    @mutation
    async def cancel_session(self, campaign_id: UUID, session_id: UUID) -> None:
        campaign = self.campaigns[campaign_id]
        session = campaign.sessions[session_id]
        session.cancelled = True
        campaign.update_session(session)

    @mutation
    async def delete_campaign(self, campaign_id: UUID) -> None:
        self.campaigns.pop(campaign_id, None)

    @mutation
    async def delete_session(self, campaign_id: UUID, session_id: UUID) -> None:
        campaign = self.campaigns[campaign_id]
        campaign.sessions.pop(session_id, None)

    async def get_upcoming_campaign_sessions(
        self, campaign_id: UUID, limit: int
    ) -> list[Session]:
        campaign = self.campaigns[campaign_id]
        return campaign.get_upcoming_sessions(limit=limit)

    async def get_campaign_sessions_history(
        self, campaign_id: UUID, limit: int
    ) -> list[Session]:
        campaign = self.campaigns[campaign_id]
        return campaign.get_sessions_history(limit=limit)

    async def get_upcoming_sessions(self, limit: int = 5) -> list[Session]:
        sessions = []
        for campaign in self.campaigns.values():
            sessions.extend(campaign.get_upcoming_sessions(limit))

        sessions.sort(key=lambda s: s.starts_at)
        return sessions[:limit]

    async def get_next_upcoming_session(self) -> Session | None:
        candidates = [
            session
            for campaign in self.campaigns.values()
            for session in campaign.sessions.values()
            if not session.cancelled and session.upcoming
        ]
        candidates.sort(key=lambda s: s.starts_at)
        return candidates[0] if candidates else None

    @mutation
    async def schedule_campaign_sessions(self, campaign_id: UUID, count: int) -> None:
        campaign = self.campaigns[campaign_id]
        for occurrence in campaign.get_next_sessions_time(count):
            session = Session(
                starts_at=occurrence,
                campaign_id=campaign_id,
                campaign_name=campaign.name,
            )
            campaign.add_session(session)

    async def get_next_unannounced_session(self, within: timedelta) -> Session | None:
        now = datetime.now(UTC)
        window_end = now + within
        candidates = [
            session
            for campaign in self.campaigns.values()
            for session in campaign.sessions.values()
            if campaign.active
            and not session.cancelled
            and not session.announced
            and now <= session.starts_at <= window_end
        ]
        candidates.sort(key=lambda s: s.starts_at)
        return candidates[0] if candidates else None

    @mutation
    async def mark_session_announced(
        self,
        campaign_id: UUID,
        session_id: UUID,
        message_id: int | None = None,
        channel_id: int | None = None,
    ):
        campaign = self.campaigns[campaign_id]
        session = campaign.sessions[session_id]
        session.announced = True
        session.announcement_message_id = message_id
        session.announcement_channel_id = channel_id
        campaign.update_session(session)

    @mutation
    async def mark_session_confirmed(self, campaign_id: UUID, session_id: UUID):
        campaign = self.campaigns[campaign_id]
        session = campaign.sessions[session_id]
        session.confirmed = True
        campaign.update_session(session)

    async def list_campaigns(self) -> list[Campaign]:
        return list(self.campaigns.values())

    async def get_campaign(self, campaign_id: UUID) -> Campaign:
        return self.campaigns[campaign_id]

    @mutation
    async def set_campaign_rrule(self, campaign_id: UUID, rrule: str) -> None:
        campaign = self.campaigns[campaign_id]
        campaign.rrule = rrule

    async def get_session(self, campaign_id: UUID, session_id: UUID) -> Session:
        campaign = self.campaigns[campaign_id]
        return campaign.sessions[session_id]

    async def get_campaigns(self) -> list[Campaign]:
        return list(self.campaigns.values())

    @mutation
    async def set_campaign_time(self, campaign_id: UUID, time: time) -> None:
        campaign = self.campaigns[campaign_id]
        campaign.time = time

    @mutation
    async def finish_campaign(self, campaign_id: UUID) -> None:
        campaign = self.campaigns[campaign_id]
        campaign.finished_at = datetime.now(UTC)
