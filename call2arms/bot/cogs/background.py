import datetime
from string import Template

from discord.ext import commands, tasks
from loguru import logger

from call2arms.bot.ui.sessions import EditSessionView
from call2arms.bot.discord_service import DiscordService
from call2arms.config import Config
from call2arms.model import Session
from call2arms.storage import DataStore

SESSION_MESSAGE = Template("""
$party_tag Do we play at <t:$ts:f>?
""")


def get_session_message(party_tag: str, session_ts: int) -> str:
    return SESSION_MESSAGE.substitute(
        party_tag=party_tag,
        ts=session_ts,
    )


class BackgroundCog(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config: Config = bot.config
        self.discord_service: DiscordService = bot.discord_service
        self.store: DataStore = bot.data_store

    async def cog_load(self) -> None:
        self.persist_data.change_interval(minutes=self.config.SAVE_INTERVAL_MINUTES)
        self.schedule_sessions.change_interval(
            hours=self.config.AUTOSCHEDULE_INTERVAL_HOURS
        )
        self.post_session_announcement.start()
        self.schedule_sessions.start()
        self.persist_data.start()
        self.post_voting_success.start()

        await self.schedule_sessions()

    async def cog_unload(self) -> None:
        self.post_session_announcement.cancel()
        self.schedule_sessions.cancel()
        self.persist_data.cancel()
        self.post_voting_success.cancel()
        await self.store.save(force=True)

    async def _post_vote(self, session: Session) -> None:
        party_tag = await self.discord_service.get_role_mention(
            guild_id=self.config.GUILD_ID, role_id=self.config.TAG_ROLE_ID
        )
        message_content = get_session_message(
            party_tag=party_tag,
            session_ts=int(session.starts_at.timestamp()),
        )
        message = await self.discord_service.send_message(
            channel_id=self.config.TARGET_CHANNEL_ID,
            message_content=message_content,
        )
        await self.discord_service.add_reaction(message, ("🐐", "🚫"))
        await self.store.mark_session_announced(
            session.campaign_id,
            session.id,
            message_id=message.id,
            channel_id=self.config.TARGET_CHANNEL_ID,
        )

    @tasks.loop(time=datetime.time(hour=14, minute=0, tzinfo=datetime.timezone.utc))
    async def post_session_announcement(self) -> None:
        window = datetime.timedelta(days=self.config.VOTE_WINDOW_DAYS)
        session = await self.store.get_next_unannounced_session(within=window)
        if session is None:
            return

        logger.info("Posting vote for session {}", session.id)
        await self._post_vote(session)

    @tasks.loop(minutes=15)
    async def persist_data(self) -> None:
        await self.store.save()

    @tasks.loop(hours=24)
    async def schedule_sessions(self) -> None:
        for campaign in await self.store.get_campaigns():
            if not campaign.active:
                continue
            await self.store.schedule_campaign_sessions(
                campaign_id=campaign.id, count=self.config.SESSIONS_PLANNING_WINDOW
            )
            logger.info("Scheduled sessions for campaign {}", campaign.id)

    @tasks.loop(hours=1)
    async def post_voting_success(self) -> None:
        for campaign in await self.store.get_campaigns():
            if not campaign.active:
                continue
            for session in campaign.get_announced_sessions():
                votes = await self.discord_service.get_reaction_users(
                    session.announcement_channel_id,
                    session.announcement_message_id,
                    "🐐",
                )
                if len(votes) >= self.config.MIN_VOTES:
                    view = await EditSessionView.create(
                        store=self.store,
                        discord_service=self.discord_service,
                        session=session,
                        editable=False,
                    )
                    message = await self.discord_service.send_view(
                        channel_id=self.config.TARGET_CHANNEL_ID,
                        view=view,
                    )
                    await self.store.mark_session_confirmed(session.campaign_id, session.id)

    @post_session_announcement.before_loop
    async def before_post_session_announcement(self) -> None:
        await self.bot.wait_until_ready()

    @schedule_sessions.before_loop
    async def before_schedule_sessions(self) -> None:
        await self.bot.wait_until_ready()

    @persist_data.before_loop
    async def before_persist_data(self) -> None:
        await self.bot.wait_until_ready()

    @post_voting_success.before_loop
    async def before_post_voting_success(self) -> None:
        await self.bot.wait_until_ready()
