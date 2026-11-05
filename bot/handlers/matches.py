from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from bot.db import SessionLocal
from bot.models import Match, Team, TeamMember, BallEvent
from bot.keyboards import (
    overs_kb, wickets_kb, team_kb,
    player_kb, bowler_kb, score_kb
)
from bot.services.event_media import send_event_media
from bot.config import settings


router = Router()

pending_overs = {}


@router.message(Command("newmatch"))
async def newmatch(message: Message):

    if message.chat.type == "private":
        await message.answer(
            "Please use /newmatch inside your cricket group."
        )
        return

    pending_overs[message.from_user.id] = 0

    await message.answer(
        "🏆 CRICKET RIVALRY\n\nSelect match overs:",
        reply_markup=overs_kb()
    )


@router.callback_query(F.data.startswith("overs:"))
async def select_overs(call: CallbackQuery):

    overs = int(call.data.split(":")[1])

    pending_overs[call.from_user.id] = overs

    await call.message.edit_text(
        f"Selected {overs} overs.\n\nSelect wickets:",
        reply_markup=wickets_kb()
    )

    await call.answer()


@router.callback_query(F.data.startswith("wickets:"))
async def select_wickets(call: CallbackQuery):

    overs = pending_overs.get(call.from_user.id)

    if not overs:
        await call.answer(
            "Start again with /newmatch",
            show_alert=True
        )
        return

    wickets = int(call.data.split(":")[1])

    async with SessionLocal() as session:

        match = Match(
            chat_id=call.message.chat.id,
            created_by=call.from_user.id,
            overs=overs,
            wickets_limit=wickets
        )

        session.add(match)
        await session.flush()

        session.add_all([
            Team(
                match_id=match.id,
                name="Team A",
                captain_id=call.from_user.id,
                side="A"
            ),
            Team(
                match_id=match.id,
                name="Team B",
                captain_id=0,
                side="B"
            )
        ])

        match_id = match.id

        await session.commit()

    await call.message.edit_text(
        f"🏏 CRICKET RIVALRY #{match_id}\n\n"
        f"Overs: {overs}\n"
        f"Wickets: {wickets}\n\n"
        "Select your team:",
        reply_markup=team_kb(match_id)
    )

    async with SessionLocal() as session:
        match = await session.get(Match, match_id)
        match.group_message_id = call.message.message_id
        await session.commit()

    await call.answer("Match created!")


@router.callback_query(F.data.startswith("join:"))
async def join_team(call: CallbackQuery):

    _, match_id, side = call.data.split(":")
    match_id = int(match_id)

    async with SessionLocal() as session:

        team = (
            await session.execute(
                select(Team).where(
                    Team.match_id == match_id,
                    Team.side == side
                )
            )
        ).scalar_one_or_none()

        if not team:
            await call.answer("Team not found.")
            return

        existing = (
            await session.execute(
                select(TeamMember).where(
                    TeamMember.team_id == team.id,
                    TeamMember.telegram_id == call.from_user.id
                )
            )
        ).scalar_one_or_none()

        if existing:
            await call.answer("Already joined!")
            return

        member = TeamMember(
            team_id=team.id,
            telegram_id=call.from_user.id,
            display_name=call.from_user.full_name,
            is_captain=(
                team.captain_id == call.from_user.id
            )
        )

        session.add(member)
        await session.commit()

    await call.answer(f"Joined Team {side}!")

    await call.message.answer(
        f"✅ {call.from_user.full_name} joined Team {side}"
    )


async def get_active_match(session, chat_id):

    result = await session.execute(
        select(Match)
        .where(
            Match.chat_id == chat_id,
            Match.status.in_(["setup", "live"])
        )
        .order_by(Match.id.desc())
    )

    return result.scalars().first()


@router.message(Command("selectbatter"))
async def select_batter(message: Message):

    async with SessionLocal() as session:

        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match.")
            return

        team = (
            await session.execute(
                select(Team).where(
                    Team.match_id == match.id,
                    Team.side == match.batting_side
                )
            )
        ).scalar_one()

        players = (
            await session.execute(
                select(TeamMember).where(
                    TeamMember.team_id == team.id
                )
            )
        ).scalars().all()

        if not players:
            await message.answer("No batting players.")
            return

        await message.answer(
            "🏏 SELECT BATSMAN",
            reply_markup=player_kb(players, "batter")
        )


@router.message(Command("selectbowler"))
async def select_bowler(message: Message):

    async with SessionLocal() as session:

        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match.")
            return

        bowling_side = (
            "B" if match.batting_side == "A" else "A"
        )

        team = (
            await session.execute(
                select(Team).where(
                    Team.match_id == match.id,
                    Team.side == bowling_side
                )
            )
        ).scalar_one()

        players = (
            await session.execute(
                select(TeamMember).where(
                    TeamMember.team_id == team.id
                )
            )
        ).scalars().all()

        if not players:
            await message.answer("No bowling players.")
            return

        await message.answer(
            "🎳 SELECT BOWLER",
            reply_markup=player_kb(players, "bowler")
        )


@router.callback_query(F.data.startswith("batter:"))
async def set_batter(call: CallbackQuery):

    player_id = int(call.data.split(":")[1])

    async with SessionLocal() as session:

        match = await get_active_match(
            session, call.message.chat.id
        )

        if not match:
            await call.answer("No active match.")
            return

        match.striker_id = player_id
        match.status = "live"

        await session.commit()

    await call.message.answer(
        f"🏏 Batsman selected: "
        f'<a href="tg://user?id={player_id}">Player</a>',
        parse_mode="HTML"
    )

    await call.answer("Batsman selected!")


@router.callback_query(F.data.startswith("bowler:"))
async def set_bowler(call: CallbackQuery):

    player_id = int(call.data.split(":")[1])

    async with SessionLocal() as session:

        match = await get_active_match(
            session, call.message.chat.id
        )

        if not match or not match.striker_id:
            await call.answer(
                "Select a batsman first.",
                show_alert=True
            )
            return

        match.bowler_id = player_id

        match_id = match.id
        chat_id = match.chat_id
        runs = match.runs
        wickets = match.wickets
        balls = match.legal_balls
        batter_id = match.striker_id
        group_message_id = match.group_message_id

        await session.commit()

    batter = (
        f'<a href="tg://user?id={batter_id}">Batsman</a>'
    )

    try:
        await call.bot.send_message(
            player_id,
            "🔔 YOUR BOWLING TURN!\n\n"
            f"Match: #{match_id}\n"
            f"Batsman: {batter}\n"
            f"Score: {runs}/{wickets}\n"
            f"Overs: {balls // 6}.{balls % 6}",
            parse_mode="HTML",
            reply_markup=bowler_kb(match_id)
        )

    except Exception:
        await call.message.answer(
            "⚠️ Bowler must start the bot using /start "
            "before receiving private notifications."
        )

    await call.message.answer(
        f"🎳 Bowler selected: "
        f'<a href="tg://user?id={player_id}">Bowler</a>',
        parse_mode="HTML"
    )

    await call.answer("Bowler selected!")


@router.callback_query(F.data.startswith("bowl:"))
async def bowl_now(call: CallbackQuery):

    match_id = int(call.data.split(":")[1])

    async with SessionLocal() as session:

        match = await session.get(Match, match_id)

        if not match:
            await call.answer("Match not found.")
            return

        if match.bowler_id != call.from_user.id:
            await call.answer(
                "This is not your bowling turn!",
                show_alert=True
            )
            return

        score = f"{match.runs}/{match.wickets}"
        over = (
            f"{match.legal_balls // 6}."
            f"{match.legal_balls % 6}"
        )

        chat_id = match.chat_id
        batter_id = match.striker_id

    caption = (
        f"🎳 BOWLING DELIVERY!\n"
        f"Batsman: <a href='tg://user?id={batter_id}'>Player</a>\n"
        f"Score: {score}\n"
        f"Overs: {over}"
    )

    if settings.bowling_video_file_id:
        await call.bot.send_video(
            chat_id,
            settings.bowling_video_file_id,
            caption=caption,
            parse_mode="HTML"
        )

    elif settings.bowling_video_url:
        await call.bot.send_video(
            chat_id,
            settings.bowling_video_url,
            caption=caption,
            parse_mode="HTML"
        )

    else:
        await call.bot.send_message(
            chat_id,
            caption + "\n⚠️ Bowling video not configured.",
            parse_mode="HTML"
        )

    await call.bot.send_message(
        chat_id,
        "🎮 SELECT DELIVERY RESULT:",
        reply_markup=score_kb(match_id)
    )

    await call.answer("Bowling delivery sent!")
