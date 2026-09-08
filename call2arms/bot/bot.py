import discord
from discord.ext import commands
from discord import app_commands
from loguru import logger

from call2arms.config import Config
from call2arms.bot.cogs import BackgroundCog, SessionsCog
from call2arms.bot.discord_service import DiscordService
from call2arms.storage import DataStore


def setup_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.guild_messages = True
    intents.guild_reactions = True
    intents.webhooks = True
    intents.members = True
    return intents


class CallToArmsBot(commands.Bot):
    def __init__(self, config: Config):
        super().__init__(command_prefix="!", intents=setup_intents())
        self.config = config
        self.discord_service = DiscordService(self)
        self.data_store = DataStore(config.DATA_PATH)

    async def setup_hook(self) -> None:
        self.data_store.load()

        self.tree.on_error = self.on_app_command_error
        await self.add_cog(BackgroundCog(self))
        await self.add_cog(SessionsCog(self))

        guild = discord.Object(id=self.config.GUILD_ID)
        self.tree.clear_commands(guild=guild)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info(
            "Synced {} guild commands: {}",
            len(synced),
            [cmd.name for cmd in synced],
        )

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
