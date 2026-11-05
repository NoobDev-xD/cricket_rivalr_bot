from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from sqlalchemy import select

from bot.db import SessionLocal
from bot.models import User


router = Router()


@router.message(CommandStart())
async def start(message: Message):

    async with SessionLocal() as session:

        result = await session.execute(
            select(User).where(
                User.telegram_id == message.from_user.id
            )
        )

        user = result.scalar_one_or_none()

        if user is None:

            session.add(
                User(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name
                )
            )

            await session.commit()

    await message.answer(
        "🏏 WELCOME TO CRICKET RIVALRY BOT!\n\n"
        "Commands:\n"
        "/newmatch - Create match\n"
        "/selectbatter - Select batsman\n"
        "/selectbowler - Select bowler\n\n"
        "You are registered!\n"
        "You can now receive bowling notifications."
    )
