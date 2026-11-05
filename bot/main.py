import asyncio

from aiogram import Bot, Dispatcher

from bot.config import settings
from bot.db import init_db

from bot.handlers import start, matches


async def main():

    await init_db()

    bot = Bot(
        token=settings.bot_token
    )

    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(matches.router)

    print("🏏 CRICKET RIVALRY BOT STARTED!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
