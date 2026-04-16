import datetime
import discord
from discord.ext import commands, tasks
from discord import app_commands
from loguru import logger

from call2arms.config import Config
from call2arms.discord_service import DiscordService
from call2arms.message import get_session_message


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

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self.config.GUILD_ID)

        self.tree.clear_commands(guild=guild)
        self.tree.on_error = self.on_app_command_error

        cmd = app_commands.Command(
            name="post_vote",
            description="Post the weekly vote message",
            callback=self.post_vote_command,
        )
        self.tree.add_command(cmd, guild=guild)

        logger.info("Local guild commands: {}", [c.name for c in self.tree.get_commands(guild=guild)])
        synced = await self.tree.sync(guild=guild)
        logger.info("Synced guild commands: {}", [c.name for c in synced])

        if not self.post_session_announcement.is_running():
            self.post_session_announcement.start()

    async def on_ready(self) -> None:
        logger.info(f"{self.user} has connected to Discord!")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.exception("App command failed: {}", error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Command failed: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Command failed: {error}", ephemeral=True)
        except Exception:
            logger.exception("Failed to send interaction error response")

    async def _post_announcement(self, force: bool = False) -> None:
        if force or datetime.datetime.utcnow().weekday() == 2:
            logger.info("Trying to post a vote")
            party_tag = await self.discord_service.get_role_mention(self.config.TAG_ROLE_ID)
            message_content = get_session_message(party_tag=party_tag)
            message = await self.discord_service.send_message(
                channel_id=self.config.TARGET_CHANNEL_ID,
                message_content=message_content,
            )
            await self.discord_service.add_reaction(message, "🐐")
            await self.discord_service.add_reaction(message, "🚫")

    async def post_vote_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._post_announcement(force=True)
        await interaction.followup.send("Done.", ephemeral=True)

    @tasks.loop(time=datetime.time(hour=14, minute=0, tzinfo=datetime.timezone.utc))
    async def post_session_announcement(self) -> None:
        await self._post_announcement()

    @post_session_announcement.before_loop
    async def before_post_session_announcement(self) -> None:
        await self.wait_until_ready()