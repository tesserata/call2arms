import discord
from discord import app_commands
from discord.ext import commands

from call2arms.bot.discord_service import DiscordService
from call2arms.bot.ui.campaigns import CampaignsView
from call2arms.bot.ui.sessions import UpcomingSessionsView
from call2arms.config import Config
from call2arms.storage import DataStore


class SessionsCog(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config: Config = bot.config
        self.discord_service: DiscordService = bot.discord_service
        self.store: DataStore = bot.data_store

    @app_commands.command(name="schedule", description="View upcoming sessions")
    async def get_schedule(self, interaction: discord.Interaction) -> None:
        view = await UpcomingSessionsView.create(store=self.store)
        await interaction.response.send_message(view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @app_commands.command(name="campaigns", description="List all campaigns")
    async def get_campaigns(self, interaction: discord.Interaction) -> None:
        view = await CampaignsView.create(store=self.store)
        await interaction.response.send_message(view=view, ephemeral=True)
        view.message = await interaction.original_response()

