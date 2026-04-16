from typing import Iterable

import discord
from discord.ext.commands.bot import Bot
from discord.utils import get

from call2arms.exceptions import (
    ChannelNotFoundException,
    RoleNotFoundException,
)


class DiscordService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def get_channel(
        self, channel_id: int
    ) -> discord.guild.TextChannel | discord.threads.Thread:
        channel = self.bot.get_channel(channel_id)
        if (
            not isinstance(channel, discord.guild.TextChannel)
            and not isinstance(channel, discord.threads.Thread)
        ) or not channel:
            raise ChannelNotFoundException(channel_id)

        return channel

    async def send_message(
        self, channel_id: int, message_content: str
    ) -> discord.Message:
        channel = await self.get_channel(channel_id)
        message = await channel.send(message_content)
        return message

    async def get_role_mention(self, role_id: int) -> str:
        role_instance = get(
            self.bot.guilds[0].roles, id=role_id
        )  # hardcoded for use in one server
        if not role_instance:
            raise RoleNotFoundException(role_id=role_id)
        return role_instance.mention

    @staticmethod
    async def add_reaction(message: discord.Message, reactions: Iterable[str]) -> None:
        for reaction in reactions:
            await message.add_reaction(reaction)
