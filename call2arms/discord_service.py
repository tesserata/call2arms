from typing import Iterable

import discord
from discord.ext.commands.bot import Bot
from discord.utils import get

from call2arms.exceptions import (
    InstanceNotFoundException,
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
            raise InstanceNotFoundException(
                instance_type="channel", instance_id=channel_id
            )

        return channel

    async def send_message(
        self, channel_id: int, message_content: str
    ) -> discord.Message:
        channel = await self.get_channel(channel_id)
        message = await channel.send(message_content)
        return message

    async def get_role_mention(self, guild_id: int, role_id: int) -> str:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise InstanceNotFoundException(instance_type="guild", instance_id=role_id)
        role_instance = get(guild.roles, id=role_id)
        if not role_instance:
            raise InstanceNotFoundException(instance_type="role", instance_id=role_id)
        return role_instance.mention

    @staticmethod
    async def add_reaction(message: discord.Message, reactions: Iterable[str]) -> None:
        for reaction in reactions:
            await message.add_reaction(reaction)
