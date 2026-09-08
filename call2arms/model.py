from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any, Iterable
from uuid import UUID, uuid4

from dateutil.rrule import rrulestr


@dataclass
class Session:
    starts_at: datetime
    scheduled_for: datetime | None = None
    cancelled: bool = False
    announced: bool = False
    confirmed: bool = False
    id: UUID = field(default_factory=uuid4)
    campaign_id: UUID | None = None
    campaign_name: str | None = None
    number: int | None = None
    announcement_message_id: int | None = None
    announcement_channel_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "starts_at": self.starts_at.timestamp(),
            "scheduled_for": (
                self.scheduled_for.timestamp() if self.scheduled_for else None
            ),
            "cancelled": self.cancelled,
            "announced": self.announced,
            "confirmed": self.confirmed,
            "id": str(self.id),
            "campaign_id": str(self.campaign_id) if self.campaign_id else None,
            "campaign_name": self.campaign_name,
            "number": self.number,
            "announcement_message_id": self.announcement_message_id,
            "announcement_channel_id": self.announcement_channel_id,
        }

    @classmethod
    def from_dict(cls, data: dict):
        starts_at = datetime.fromtimestamp(data["starts_at"], UTC)
        scheduled_for = (
            datetime.fromtimestamp(data["scheduled_for"], UTC)
            if data.get("scheduled_for")
            else starts_at
        )
        return cls(
            starts_at=starts_at,
            scheduled_for=scheduled_for,
            cancelled=data.get("cancelled", False),
            announced=data.get("announced", False),
            confirmed=data.get("confirmed", False),
            id=UUID(data["id"]),
            campaign_id=UUID(data["campaign_id"]) if data.get("campaign_id") else None,
            campaign_name=data.get("campaign_name"),
            number=data.get("number"),
            announcement_message_id=data.get("announcement_message_id"),
            announcement_channel_id=data.get("announcement_channel_id"),
        )

    @property
    def upcoming(self) -> bool:
        return self.starts_at >= datetime.now(UTC)

    @property
    def completed(self) -> bool:
        return self.starts_at < datetime.now(UTC) and not self.cancelled

    @property
    def status(self) -> str:
        if self.cancelled:
            return "Cancelled"
        if self.completed:
            return "Completed"
        if self.confirmed:
            return "Confirmed"
        if self.announced:
            return "Announced"
        return "Scheduled"

    def __str__(self) -> str:
        return f"{self.campaign_name} session #{self.number} – <t:{int(self.starts_at.timestamp())}:f> {'(cancelled)' if self.cancelled else ''}"


@dataclass
class Campaign:
    name: str
    started_at: datetime
    finished_at: datetime | None = None
    sessions: dict[UUID, Session] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    time: time = time(15, 30)
    rrule: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "active": self.active,
            "started_at": self.started_at.timestamp(),
            "finished_at": self.finished_at.timestamp() if self.finished_at else None,
            "sessions": [s.to_dict() for s in self.sessions.values()],
            "id": str(self.id),
            "time": self.time.strftime("%H:%M"),
            "rrule": self.rrule,
        }

    @property
    def active(self) -> bool:
        return self.finished_at is None

    @property
    def sessions_count(self) -> int:
        return len([s for s in self.sessions.values() if not s.cancelled])

    @property
    def past_sessions_count(self) -> int:
        return len([s for s in self.sessions.values() if not s.upcoming and not s.cancelled])

    @property
    def upcoming_sessions_count(self) -> int:
        return len([s for s in self.sessions.values() if s.upcoming and not s.cancelled])

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            started_at=datetime.fromtimestamp(data["started_at"], UTC),
            finished_at=(
                datetime.fromtimestamp(data["finished_at"], UTC)
                if data["finished_at"]
                else None
            ),
            sessions={UUID(s["id"]): Session.from_dict(s) for s in data["sessions"]},
            id=UUID(data["id"]),
            time=datetime.strptime(data["time"], "%H:%M").time(),
            rrule=data["rrule"],
        )

    def add_session(self, session: Session) -> None:
        session.campaign_id = self.id
        session.campaign_name = self.name
        self.sessions[session.id] = session
        self._enumerate_sessions()

    def _enumerate_sessions(self) -> None:
        all_sessions = list(self.sessions.values())
        all_sessions.sort(key=lambda s: s.starts_at)
        non_cancelled = [s for s in all_sessions if not s.cancelled]
        for num, session in enumerate(non_cancelled):
            self.sessions[session.id].number = num + 1

    def get_upcoming_sessions(self, limit=4) -> list[Session]:
        upcoming_sessions = [
            s for s in self.sessions.values() if s.upcoming and not s.cancelled
        ]
        upcoming_sessions.sort(key=lambda s: s.starts_at)
        return upcoming_sessions[:limit]

    def get_announced_sessions(self) -> list[Session]:
        announced_sessions = [
            s
            for s in self.sessions.values()
            if s.announced and not s.cancelled and s.upcoming
        ]
        announced_sessions.sort(key=lambda s: s.starts_at)
        return announced_sessions

    def get_sessions_history(self, limit=10) -> list[Session]:
        past_sessions = [
            s for s in self.sessions.values() if not s.upcoming and not s.cancelled
        ]
        past_sessions.sort(key=lambda s: s.starts_at, reverse=True)
        return past_sessions[:limit]

    def update_session(self, session: Session) -> None:
        self.sessions[session.id] = session
        self._enumerate_sessions()

    def get_next_sessions_time(self, count: int) -> Iterable[datetime]:
        if not self.rrule:
            return

        scheduled_dates = {(s.scheduled_for or s.starts_at).date() for s in self.sessions.values()}
        rule = rrulestr(self.rrule, dtstart=self.started_at)

        upcoming = [s for s in self.sessions.values() if s.upcoming and not s.cancelled]
        counter = count - len(upcoming)
        if counter > 0:
            for occ in rule.xafter(
                datetime.now(UTC), count=count + len(scheduled_dates), inc=False
            ):
                starts_at = occ.replace(
                    hour=self.time.hour,
                    minute=self.time.minute,
                    second=0,
                    microsecond=0,
                )
                if starts_at.date() in scheduled_dates:
                    continue

                counter -= 1
                if counter < 0:
                    break

                yield starts_at
