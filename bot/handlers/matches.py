from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from sqlalchemy import select

from bot.db import SessionLocal
from bot.models import Match, Team, TeamMember, BallEvent
from bot.keyboards import (
    overs_kb, wickets_kb, team_kb, player_kb,
    bowler_kb, score_kb
)
from bot.services.event_media import send_event_media
from bot.config import settings

router = Router()
pending_overs = {}


# ============== KEYBOARDS ==============

def admin_kb(match_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="👑 Change Host",
                callback_data=f"admin:host:{match_id}"
            )
        ]
    ])


def host_kb(match_id, players):
    unique = {
        p.telegram_id: p for p in players
    }

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=p.display_name[:60],
                callback_data=f"hostset:{match_id}:{p.telegram_id}"
            )
        ]
        for p in unique.values()
    ])


def captain_kb(match_id, teams):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Team {team.side} — {team.name}",
                callback_data=f"captainteam:{match_id}:{team.id}"
            )
        ]
        for team in teams
    ])


# ============== PERMISSIONS ==============

async def get_active_match(session, chat_id):
    result = await session.execute(
        select(Match).where(
            Match.chat_id == chat_id,
            Match.status.in_(["setup", "live"])
        ).order_by(Match.id.desc())
    )
    return result.scalars().first()


async def is_group_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(
            chat_id, user_id
        )
        return member.status in (
            "creator", "administrator"
        )
    except Exception:
        return False


async def is_host_or_admin(bot, match, user_id):
    if user_id == match.host_id:
        return True

    return await is_group_admin(
        bot, match.chat_id, user_id
    )


async def is_host_or_captain(session, match, user_id):
    if user_id == match.host_id:
        return True

    result = await session.execute(
        select(Team.id).where(
            Team.match_id == match.id,
            Team.captain_id == user_id
        )
    )
    return result.first() is not None


async def require_host_or_admin(call, match):
    if not await is_host_or_admin(
        call.bot, match, call.from_user.id
    ):
        await call.answer(
            "⛔ Only Host / Group Admin can do this!",
            show_alert=True
        )
        return False

    return True


async def require_host_or_captain(call, session, match):
    if not await is_host_or_captain(
        session, match, call.from_user.id
    ):
        await call.answer(
            "⛔ Only Host / Captain can do this!",
            show_alert=True
        )
        return False

    return True


async def require_group_message(call, match):
    if not call.message:
        await call.answer(
            "Invalid message",
            show_alert=True
        )
        return False

    if call.message.chat.id != match.chat_id:
        await call.answer(
            "⛔ Use this button in the match group!",
            show_alert=True
        )
        return False

    return True


def parse_callback_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

# ============== CREATE MATCH ==============

@router.message(Command("newmatch"))
async def new_match(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer(
            "Create a match inside your Telegram group."
        )
        return

    async with SessionLocal() as session:
        active = await get_active_match(
            session, message.chat.id
        )

        if active:
            await message.answer(
                "A match is already running or being set up."
            )
            return

        match = Match(
            chat_id=message.chat.id,
            created_by=message.from_user.id,
            host_id=message.from_user.id,
            overs=0,
            wickets_limit=0,
            status="setup"
        )

        session.add(match)
        await session.commit()
        await session.refresh(match)

        await message.answer(
            "🏏 New match created!\n\n"
            "Choose the number of overs:",
            reply_markup=overs_kb()
        )


# ============== SELECT OVERS ==============

@router.callback_query(F.data.startswith("overs:"))
async def set_overs(call: CallbackQuery):
    value = parse_callback_int(
        call.data.split(":")[1]
    )

    if value not in (2, 5, 10, 15, 20, 50):
        await call.answer(
            "Invalid overs selection!",
            show_alert=True
        )
        return

    async with SessionLocal() as session:
        match = await get_active_match(
            session, call.message.chat.id
        )

        if not match or match.status != "setup":
            await call.answer(
                "No match setup found!",
                show_alert=True
            )
            return

        if match.created_by != call.from_user.id:
            await call.answer(
                "Only match creator can set overs!",
                show_alert=True
            )
            return

        match.overs = value
        await session.commit()

        await call.message.edit_text(
            f"🏏 Overs selected: {value}\n\n"
            "Choose wickets:",
            reply_markup=wickets_kb()
        )

        await call.answer()


# ============== SELECT WICKETS ==============

@router.callback_query(F.data.startswith("wickets:"))
async def set_wickets(call: CallbackQuery):
    value = parse_callback_int(
        call.data.split(":")[1]
    )

    if value not in (1, 2, 5, 10):
        await call.answer(
            "Invalid wickets selection!",
            show_alert=True
        )
        return

    async with SessionLocal() as session:
        match = await get_active_match(
            session, call.message.chat.id
        )

        if not match or match.status != "setup":
            await call.answer(
                "No match setup found!",
                show_alert=True
            )
            return

        if match.created_by != call.from_user.id:
            await call.answer(
                "Only match creator can set wickets!",
                show_alert=True
            )
            return

        if not match.overs:
            await call.answer(
                "Select overs first!",
                show_alert=True
            )
            return

        match.wickets_limit = value
        await session.commit()

        await call.message.edit_text(
            f"🏏 Match Settings\n"
            f"Overs: {match.overs}\n"
            f"Wickets: {value}\n\n"
            "Teams can now join!",
            reply_markup=team_kb(match.id)
        )

        await call.answer()


# ============== JOIN TEAM ==============

@router.callback_query(F.data.startswith("join:"))
async def join_team(call: CallbackQuery):
    parts = call.data.split(":")
    match_id = parse_callback_int(parts[1])
    side = parts[2] if len(parts) > 2 else None

    if side not in ("A", "B") or not match_id:
        await call.answer(
            "Invalid team selection!",
            show_alert=True
        )
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(Match.id == match_id)
        )
        match = result.scalar_one_or_none()

        if not match or match.status != "setup":
            await call.answer(
                "Match is not accepting players!",
                show_alert=True
            )
            return

        if not await require_group_message(call, match):
            return

        result = await session.execute(
            select(Team).where(
                Team.match_id == match.id,
                Team.side == side
            )
        )
        team = result.scalar_one_or_none()

        if not team:
            team = Team(
                match_id=match.id,
                name=f"Team {side}",
                side=side,
                captain_id=0
            )
            session.add(team)
            await session.flush()

        result = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.telegram_id ==
                call.from_user.id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            await call.answer(
                "You already joined this team!",
                show_alert=True
            )
            return

        player = TeamMember(
            team_id=team.id,
            telegram_id=call.from_user.id,
            display_name=(
                call.from_user.full_name[:128]
            ),
            is_captain=False
        )

        session.add(player)
        await session.commit()

        await call.answer(
            f"Joined Team {side}!"
        )

# ============== CREATE MATCH ==============

@router.message(Command("newmatch"))
async def new_match(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer(
            "⛔ Create match in a group only!"
        )
        return

    async with SessionLocal() as session:
        active = await get_active_match(
            session, message.chat.id
        )

        if active:
            await message.answer(
                "⚠️ A match is already active!"
            )
            return

        if not await is_group_admin(
            message.bot,
            message.chat.id,
            message.from_user.id
        ):
            await message.answer(
                "⛔ Only Group Admin can create a match!"
            )
            return

        pending_overs[
            (message.chat.id, message.from_user.id)
        ] = {
            "overs": 0,
            "message_id": message.message_id
        }

        await message.answer(
            "🏏 Select match overs:",
            reply_markup=overs_kb()
        )


@router.callback_query(F.data.startswith("overs:"))
async def set_overs(call: CallbackQuery):
    parts = call.data.split(":")
    overs = parse_callback_int(parts[1])

    if not overs or overs < 1:
        await call.answer(
            "Invalid overs!",
            show_alert=True
        )
        return

    key = (
        call.message.chat.id,
        call.from_user.id
    )

    data = pending_overs.get(key)

    if not data:
        await call.answer(
            "⛔ Only match creator can select overs!",
            show_alert=True
        )
        return

    data["overs"] = overs

    await call.message.edit_text(
        f"🏏 Overs selected: {overs}\n"
        "Select wickets:",
        reply_markup=wickets_kb()
    )

    await call.answer()


@router.callback_query(F.data.startswith("wickets:"))
async def set_wickets(call: CallbackQuery):
    parts = call.data.split(":")
    wickets = parse_callback_int(parts[1])

    if not wickets or wickets < 1:
        await call.answer(
            "Invalid wickets!",
            show_alert=True
        )
        return

    key = (
        call.message.chat.id,
        call.from_user.id
    )

    data = pending_overs.get(key)

    if not data or not data.get("overs"):
        await call.answer(
            "⛔ Only match creator can do this!",
            show_alert=True
        )
        return

    overs = data["overs"]

    async with SessionLocal() as session:
        active = await get_active_match(
            session, call.message.chat.id
        )

        if active:
            pending_overs.pop(key, None)
            await call.answer(
                "A match is already active!",
                show_alert=True
            )
            return

        match = Match(
            chat_id=call.message.chat.id,
            created_by=call.from_user.id,
            host_id=call.from_user.id,
            overs=overs,
            wickets_limit=wickets,
            status="setup"
        )

        session.add(match)
        await session.flush()

        team_a = Team(
            match_id=match.id,
            name="Team A",
            captain_id=0,
            side="A"
        )

        team_b = Team(
            match_id=match.id,
            name="Team B",
            captain_id=0,
            side="B"
        )

        session.add_all([team_a, team_b])
        await session.commit()

        match_id = match.id

    pending_overs.pop(key, None)

    await call.message.edit_text(
        f"🏏 Match #{match_id} created!\n"
        f"Overs: {overs}\n"
        f"Wickets: {wickets}\n\n"
        "Players, join your teams:",
        reply_markup=team_kb(match_id)
    )

    await call.answer("Match created!")


# ============== JOIN TEAM ==============

@router.callback_query(F.data.startswith("join:"))
async def join_team(call: CallbackQuery):
    parts = call.data.split(":")

    match_id = parse_callback_int(parts[1])
    side = parts[2]

    if not match_id or side not in ("A", "B"):
        await call.answer(
            "Invalid team!",
            show_alert=True
        )
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )
        match = result.scalars().first()

        if not match or match.status != "setup":
            await call.answer(
                "Match is not available!",
                show_alert=True
            )
            return

        result = await session.execute(
            select(Team).where(
                Team.match_id == match_id,
                Team.side == side
            )
        )
        team = result.scalars().first()

        if not team:
            await call.answer(
                "Team not found!",
                show_alert=True
            )
            return

        result = await session.execute(
            select(TeamMember).where(
                TeamMember.telegram_id ==
                call.from_user.id,
                TeamMember.team_id.in_(
                    select(Team.id).where(
                        Team.match_id == match_id
                    )
                )
            )
        )
        existing = result.scalars().first()

        if existing:
            await call.answer(
                "You already joined a team!",
                show_alert=True
            )
            return

        member = TeamMember(
            team_id=team.id,
            telegram_id=call.from_user.id,
            display_name=(
                call.from_user.full_name[:128]
            ),
            is_captain=False
        )

        session.add(member)
        await session.commit()

    await call.answer(
        f"Joined Team {side}!",
        show_alert=True
    )

# ============== ADMIN PANEL ==============

@router.message(Command("admin"))
async def admin_panel(message: Message):
    async with SessionLocal() as session:
        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match!")
            return

        if not await is_group_admin(
            message.bot,
            message.chat.id,
            message.from_user.id
        ):
            await message.answer(
                "⛔ Only Group Admin can open this panel!"
            )
            return

        await message.answer(
            "🛠 ADMIN PANEL",
            reply_markup=admin_kb(match.id)
        )


@router.callback_query(F.data.startswith("admin:host:"))
async def admin_change_host(call: CallbackQuery):
    match_id = parse_callback_int(
        call.data.split(":")[2]
    )

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )
        match = result.scalars().first()

        if not match:
            await call.answer(
                "Match not found!",
                show_alert=True
            )
            return

        if not await require_group_message(call, match):
            return

        if not await require_host_or_admin(call, match):
            return

        result = await session.execute(
            select(TeamMember).join(Team).where(
                Team.match_id == match.id
            )
        )
        players = result.scalars().all()

        if not players:
            await call.answer(
                "No players joined yet!",
                show_alert=True
            )
            return

        await call.message.answer(
            "👑 Select new Host:",
            reply_markup=host_kb(match.id, players)
        )

    await call.answer()


@router.callback_query(F.data.startswith("hostset:"))
async def set_new_host(call: CallbackQuery):
    parts = call.data.split(":")
    match_id = parse_callback_int(parts[1])
    new_host = parse_callback_int(parts[2])

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )
        match = result.scalars().first()

        if not match:
            await call.answer(
                "Match not found!",
                show_alert=True
            )
            return

        if not await require_group_message(call, match):
            return

        if not await require_host_or_admin(call, match):
            return

        result = await session.execute(
            select(TeamMember).join(Team).where(
                Team.match_id == match.id,
                TeamMember.telegram_id == new_host
            )
        )
        player = result.scalars().first()

        if not player:
            await call.answer(
                "Player not found!",
                show_alert=True
            )
            return

        match.host_id = new_host
        await session.commit()

    await call.message.edit_text(
        "✅ Host changed successfully!"
    )
    await call.answer("Host updated!")


# ============== CAPTAIN PANEL ==============

@router.message(Command("captainpanel"))
async def captain_panel(message: Message):
    async with SessionLocal() as session:
        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match!")
            return

        if not await is_host_or_captain(
            session, match, message.from_user.id
        ):
            await message.answer(
                "⛔ Only Host / Captain can open this panel!"
            )
            return

        result = await session.execute(
            select(Team).where(
                Team.match_id == match.id
            )
        )
        teams = result.scalars().all()

        await message.answer(
            "🏏 CAPTAIN PANEL\nSelect team:",
            reply_markup=captain_kb(match.id, teams)
        )


@router.callback_query(F.data.startswith("captainteam:"))
async def choose_captain_team(call: CallbackQuery):
    parts = call.data.split(":")
    match_id = parse_callback_int(parts[1])
    team_id = parse_callback_int(parts[2])

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )
        match = result.scalars().first()

        if not match:
            await call.answer(
                "Match not found!",
                show_alert=True
            )
            return

        if not await require_group_message(call, match):
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        result = await session.execute(
            select(Team).where(
                Team.id == team_id,
                Team.match_id == match.id
            )
        )
        team = result.scalars().first()

        if not team:
            await call.answer(
                "Team not found!",
                show_alert=True
            )
            return

        result = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id
            )
        )
        players = result.scalars().all()

        if not players:
            await call.answer(
                "No players in this team!",
                show_alert=True
            )
            return

        buttons = [
            [
                InlineKeyboardButton(
                    text=p.display_name[:60],
                    callback_data=(
                        f"captainset:{match.id}:"
                        f"{team.id}:{p.telegram_id}"
                    )
                )
            ]
            for p in players
        ]

        await call.message.answer(
            f"👑 Select captain for {team.name}:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=buttons
            )
        )

    await call.answer()


@router.callback_query(F.data.startswith("captainset:"))
async def set_new_captain(call: CallbackQuery):
    parts = call.data.split(":")
    match_id = parse_callback_int(parts[1])
    team_id = parse_callback_int(parts[2])
    player_id = parse_callback_int(parts[3])

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )
        match = result.scalars().first()

        if not match:
            await call.answer(
                "Match not found!",
                show_alert=True
            )
            return

        if not await require_group_message(call, match):
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        result = await session.execute(
            select(Team).where(
                Team.id == team_id,
                Team.match_id == match.id
            )
        )
        team = result.scalars().first()

        if not team:
            await call.answer(
                "Team not found!",
                show_alert=True
            )
            return

        result = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.telegram_id == player_id
            )
        )
        player = result.scalars().first()

        if not player:
            await call.answer(
                "Player not found!",
                show_alert=True
            )
            return

        team.captain_id = player_id

        result = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id
            )
        )
        members = result.scalars().all()

        for member in members:
            member.is_captain = (
                member.telegram_id == player_id
            )

        await session.commit()

    await call.message.edit_text(
        f"✅ {player.display_name} is now captain "
        f"of {team.name}!"
    )
    await call.answer("Captain updated!")

# ============== SELECT BATSMAN ==============

@router.message(Command("selectbatter"))
async def select_batter(message: Message):
    async with SessionLocal() as session:
        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match!")
            return

        if not await is_host_or_captain(
            session, match, message.from_user.id
        ):
            await message.answer(
                "⛔ Only Host / Captain can select batsman!"
            )
            return

        result = await session.execute(
            select(Team).where(
                Team.match_id == match.id,
                Team.side == match.batting_side
            )
        )
        team = result.scalars().first()

        if not team:
            await message.answer("Batting team not found!")
            return

        result = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id
            )
        )
        players = result.scalars().all()

        if not players:
            await message.answer("No players in batting team!")
            return

        buttons = [
            [
                InlineKeyboardButton(
                    text=p.display_name[:60],
                    callback_data=(
                        f"setbatter:{match.id}:{p.telegram_id}"
                    )
                )
            ]
            for p in players
        ]

        await message.answer(
            "🏏 Select batsman:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=buttons
            )
        )


@router.callback_query(F.data.startswith("setbatter:"))
async def set_batter(call: CallbackQuery):
    parts = call.data.split(":")
    match_id = parse_callback_int(parts[1])
    player_id = parse_callback_int(parts[2])

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(Match.id == match_id)
        )
        match = result.scalars().first()

        if not match:
            await call.answer("Match not found!", show_alert=True)
            return

        if not await require_group_message(call, match):
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        result = await session.execute(
            select(TeamMember).join(Team).where(
                Team.match_id == match.id,
                Team.side == match.batting_side,
                TeamMember.telegram_id == player_id
            )
        )
        player = result.scalars().first()

        if not player:
            await call.answer(
                "Select a player from batting team!",
                show_alert=True
            )
            return

        if player_id == match.non_striker_id:
            await call.answer(
                "This player is already non-striker!",
                show_alert=True
            )
            return

        match.striker_id = player_id
        await session.commit()

    await call.message.edit_text(
        f"🏏 Striker: {player.display_name}"
    )
    await call.answer("Batsman selected!")


# ============== SELECT BOWLER ==============

@router.message(Command("selectbowler"))
async def select_bowler(message: Message):
    async with SessionLocal() as session:
        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match!")
            return

        if not await is_host_or_captain(
            session, match, message.from_user.id
        ):
            await message.answer(
                "⛔ Only Host / Captain can select bowler!"
            )
            return

        bowling_side = (
            "B" if match.batting_side == "A" else "A"
        )

        result = await session.execute(
            select(Team).where(
                Team.match_id == match.id,
                Team.side == bowling_side
            )
        )
        team = result.scalars().first()

        if not team:
            await message.answer("Bowling team not found!")
            return

        result = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id
            )
        )
        players = result.scalars().all()

        if not players:
            await message.answer("No players in bowling team!")
            return

        buttons = [
            [
                InlineKeyboardButton(
                    text=p.display_name[:60],
                    callback_data=(
                        f"setbowler:{match.id}:{p.telegram_id}"
                    )
                )
            ]
            for p in players
        ]

        await message.answer(
            "🎯 Select bowler:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=buttons
            )
        )


@router.callback_query(F.data.startswith("setbowler:"))
async def set_bowler(call: CallbackQuery):
    parts = call.data.split(":")
    match_id = parse_callback_int(parts[1])
    player_id = parse_callback_int(parts[2])

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(Match.id == match_id)
        )
        match = result.scalars().first()

        if not match:
            await call.answer("Match not found!", show_alert=True)
            return

        if not await require_group_message(call, match):
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        bowling_side = (
            "B" if match.batting_side == "A" else "A"
        )

        result = await session.execute(
            select(TeamMember).join(Team).where(
                Team.match_id == match.id,
                Team.side == bowling_side,
                TeamMember.telegram_id == player_id
            )
        )
        player = result.scalars().first()

        if not player:
            await call.answer(
                "Select a player from bowling team!",
                show_alert=True
            )
            return

        match.bowler_id = player_id
        await session.commit()

    await call.message.edit_text(
        f"🎯 Bowler: {player.display_name}"
    )
    await call.answer("Bowler selected!")

# ============== START BOWLING ==============

@router.callback_query(F.data.startswith("bowl:"))
async def bowl_now(call: CallbackQuery):
    match_id = parse_callback_int(
        call.data.split(":")[1]
    )

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )
        match = result.scalars().first()

        if not match:
            await call.answer(
                "Match not found!",
                show_alert=True
            )
            return

        if not await require_group_message(call, match):
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        if not match.striker_id:
            await call.answer(
                "Select batsman first!",
                show_alert=True
            )
            return

        if not match.bowler_id:
            await call.answer(
                "Select bowler first!",
                show_alert=True
            )
            return

        match.status = "live"
        await session.commit()

        striker_id = match.striker_id
        bowler_id = match.bowler_id

    await call.message.answer(
        "🏏 MATCH LIVE!\n"
        f"Striker ID: {striker_id}\n"
        f"Bowler ID: {bowler_id}",
        reply_markup=score_kb(match_id)
    )

    await call.answer("Bowling started!")


# ============== SCORE BUTTONS ==============

@router.callback_query(F.data.startswith("run:"))
async def score_run(call: CallbackQuery):
    parts = call.data.split(":")
    match_id = parse_callback_int(parts[1])
    runs = parse_callback_int(parts[2])

    if runs not in (0, 1, 2, 3, 4, 6):
        await call.answer(
            "Invalid runs!",
            show_alert=True
        )
        return

    await update_score(
        call,
        match_id,
        runs=runs
    )


@router.callback_query(F.data.startswith("wicket:"))
async def score_wicket(call: CallbackQuery):
    match_id = parse_callback_int(
        call.data.split(":")[1]
    )

    await update_score(
        call,
        match_id,
        wicket=True
    )


@router.callback_query(F.data.startswith("extra:"))
async def score_extra(call: CallbackQuery):
    parts = call.data.split(":")
    match_id = parse_callback_int(parts[1])
    extra_type = parts[2]

    if extra_type not in ("wide", "noball"):
        await call.answer(
            "Invalid extra!",
            show_alert=True
        )
        return

    await update_score(
        call,
        match_id,
        extra_type=extra_type
    )

# ============== UPDATE SCORE ==============

async def update_score(
    call,
    match_id,
    runs=0,
    wicket=False,
    extra_type=None
):
    if not match_id:
        await call.answer(
            "Invalid match!",
            show_alert=True
        )
        return

    async with SessionLocal() as session:
        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )
        match = result.scalars().first()

        if not match or match.status != "live":
            await call.answer(
                "Match is not live!",
                show_alert=True
            )
            return

        if not await require_group_message(call, match):
            return

        # Only selected bowler can score
        if call.from_user.id != match.bowler_id:
            await call.answer(
                "⛔ Only selected bowler can score!",
                show_alert=True
            )
            return

        if not match.striker_id:
            await call.answer(
                "Select next batsman first!",
                show_alert=True
            )
            return

        if not match.bowler_id:
            await call.answer(
                "Select bowler first!",
                show_alert=True
            )
            return

        if runs not in (0, 1, 2, 3, 4, 6):
            await call.answer(
                "Invalid runs!",
                show_alert=True
            )
            return

        if extra_type not in (None, "wide", "noball"):
            await call.answer(
                "Invalid extra!",
                show_alert=True
            )
            return

        if wicket and extra_type:
            await call.answer(
                "Invalid ball event!",
                show_alert=True
            )
            return

        old_balls = match.legal_balls

        over_number = (old_balls // 6) + 1
        ball_number = (old_balls % 6) + 1

        # Calculate total runs
        total_runs = runs

        if extra_type in ("wide", "noball"):
            total_runs += 1

        match.runs += total_runs

        if extra_type is None:
            match.batter_runs += runs

        match.partnership_runs += total_runs

        # Record ball event
        event = BallEvent(
            match_id=match.id,
            over_number=over_number,
            ball_number=ball_number,
            batter_id=match.striker_id,
            bowler_id=match.bowler_id,
            runs=total_runs,
            extra_type=extra_type,
            wicket=wicket
        )

        session.add(event)

        # Legal ball count
        if extra_type is None:
            match.legal_balls += 1

        # Wicket
        if wicket:
            match.wickets += 1
            match.striker_id = None
            match.bowler_id = None
            match.partnership_runs = 0

        # Check innings completion
        max_balls = match.overs * 6

        if (
            match.wickets >= match.wickets_limit
            or match.legal_balls >= max_balls
        ):
            match.status = "completed"

        await session.commit()

        current_runs = match.runs
        current_wickets = match.wickets
        current_balls = match.legal_balls
        current_overs = (
            f"{current_balls // 6}."
            f"{current_balls % 6}"
        )
        current_status = match.status

    # Send score update
    if current_status == "completed":
        await call.message.answer(
            "🏆 INNINGS COMPLETED!\n\n"
            f"Score: {current_runs}/{current_wickets}\n"
            f"Overs: {current_overs}"
        )

        await call.message.edit_reply_markup(
            reply_markup=None
        )

    elif wicket:
        await call.message.answer(
            "🔴 WICKET!\n"
            f"Score: {current_runs}/{current_wickets}\n"
            f"Overs: {current_overs}\n\n"
            "Select next batsman and bowler."
        )

        await call.message.edit_reply_markup(
            reply_markup=None
        )

    else:
        await call.message.answer(
            f"🏏 SCORE: {current_runs}/{current_wickets}\n"
            f"Overs: {current_overs}"
        )

    await call.answer("Score updated!")
