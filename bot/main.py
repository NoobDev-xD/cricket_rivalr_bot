import asyncio

from aiogram import Bot, Dispatcher

from bot.config import settings
from bot.db import init_db, close_db

from bot.handlers import start, matches


async def main():

    bot = Bot(token=settings.bot_token)

    try:
        await init_db()

        dp = Dispatcher()

        dp.include_router(start.router)
        dp.include_router(matches.router)

        print("🏏 CRICKET RIVALRY BOT STARTED!")

        await dp.start_polling(bot)

    finally:
        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
