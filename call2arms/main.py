#!/usr/bin/env python3
import asyncio

from call2arms.bot import CallToArmsBot
from call2arms.config import get_config


async def main() -> None:
    config = get_config()
    print(config.DISCORD_TOKEN)
    bot = CallToArmsBot(config)

    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())