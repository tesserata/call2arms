from typing import Iterable
from venv import logger

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

    async def send_view(
        self, channel_id: int, view: discord.ui.View
    ) -> discord.Message:
        channel = await self.get_channel(channel_id)
        message = await channel.send(view=view)
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

    async def get_reaction_users(
        self,
        channel_id: int,
        message_id: int,
        emoji: str,
        target_role: int | None = None,
    ) -> list[discord.User]:
        try:
            channel = await self.get_channel(channel_id)
            message = await channel.fetch_message(message_id)
            for reaction in message.reactions:
                if str(reaction.emoji) == emoji:
                    users = [u async for u in reaction.users() if not u.bot]
                    if target_role:
                        users = [u for u in users if get(u.roles, id=target_role)]

                    return users
        except Exception as e:
            logger.exception(e)

        return []
