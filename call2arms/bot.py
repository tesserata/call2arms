import datetime
import discord
from discord.ext import commands, tasks
from discord import app_commands
from loguru import logger

from call2arms.config import Config, VoteWeekParity
from call2arms.discord_service import DiscordService
from call2arms.message import get_session_message
from call2arms.utility import check_schedule


def setup_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.guild_messages = True
    intents.guild_reactions = True
    intents.webhooks = True
    return intents


class CallToArmsBot(commands.Bot):
    def __init__(self, config: Config):
        super().__init__(command_prefix="!", intents=setup_intents())
        self.config = config
        self.discord_service = DiscordService(self)
        self._vote_week_parity: VoteWeekParity = config.DEFAULT_WEEK_VOTE

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self.config.GUILD_ID)

        self.tree.clear_commands(guild=guild)
        self.tree.on_error = self.on_app_command_error

        post_vote_cmd = app_commands.Command(
            name="post_vote",
            description="Post the weekly vote message",
            callback=self.post_vote_command,
        )
        self.tree.add_command(post_vote_cmd, guild=guild)

        set_vote_week_cmd = app_commands.Command(
            name="set_vote_week",
            description="Set whether the scheduled vote posts on even or odd weeks",
            callback=self.set_vote_week_command,
        )
        self.tree.add_command(set_vote_week_cmd, guild=guild)

        if not self.post_session_announcement.is_running():
            self.post_session_announcement.start()

    async def on_ready(self) -> None:
        logger.info(f"{self.user} has connected to Discord!")
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="You must gather your party before venturing forth",
        )
        await self.change_presence(activity=activity)
        logger.info(f"Presence set")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.exception("App command failed: {}", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"Command failed: {error}", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Command failed: {error}", ephemeral=True
                )
        except Exception:
            logger.exception("Failed to send interaction error response")

    async def _post_announcement(self, force: bool = False) -> None:
        if force or check_schedule(target_parity=self._vote_week_parity):
            logger.info("Trying to post a vote")
            party_tag = await self.discord_service.get_role_mention(
                guild_id=self.config.GUILD_ID, role_id=self.config.TAG_ROLE_ID
            )
            message_content = get_session_message(party_tag=party_tag)
            message = await self.discord_service.send_message(
                channel_id=self.config.TARGET_CHANNEL_ID,
                message_content=message_content,
            )
            await self.discord_service.add_reaction(message, ("🐐", "🚫"))

    async def post_vote_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._post_announcement(force=True)
        await interaction.followup.send("Done", ephemeral=True)

    async def set_vote_week_command(
        self,
        interaction: discord.Interaction,
        parity: VoteWeekParity,
    ) -> None:
        self._vote_week_parity = parity

        now = datetime.datetime.now(datetime.timezone.utc)
        current_week = now.isocalendar().week

        await interaction.response.send_message(
            (
                f"Scheduled vote is now set to {parity} weeks.\n"
                f"Current week is {current_week}."
            ),
        )

    @tasks.loop(time=datetime.time(hour=14, minute=0, tzinfo=datetime.timezone.utc))
    async def post_session_announcement(self) -> None:
        await self._post_announcement()

    @post_session_announcement.before_loop
    async def before_post_session_announcement(self) -> None:
        await self.wait_until_ready()
