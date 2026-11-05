
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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


# ---------------- KEYBOARDS ----------------

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
    unique = {p.telegram_id: p for p in players}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=p.display_name[:60],
            callback_data=f"hostset:{match_id}:{p.telegram_id}"
        )]
        for p in unique.values()
    ])


def captain_kb(match_id, teams):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Team {team.side} — {team.name}",
            callback_data=f"captainteam:{match_id}:{team.id}"
        )]
        for team in teams
    ])


# ---------------- PERMISSIONS ----------------

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
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


async def is_host_or_admin(bot, match, user_id):
    return (
        user_id == match.host_id
        or await is_group_admin(bot, match.chat_id, user_id)
    )


async def is_host_or_captain(session, match, user_id):
    if user_id == match.host_id:
        return True

    teams = (await session.execute(
        select(Team).where(
            Team.match_id == match.id,
            Team.captain_id == user_id
        )
    )).scalars().all()

    return bool(teams)


async def require_host_or_admin(call, match):
    if not await is_host_or_admin(
        call.bot, match, call.from_user.id
    ):
        await call.answer(
            "Only Host / Group Admin",
            show_alert=True
        )
        return False

    return True


async def require_host_or_captain(call, session, match):
    if not await is_host_or_captain(
        session, match, call.from_user.id
    ):
        await call.answer(
            "Only Host / Captain",
            show_alert=True
        )
        return False

    return True


# ---------------- CREATE MATCH ----------------

@router.message(Command("newmatch"))
async def newmatch(message: Message):

    if message.chat.type == "private":
        await message.answer(
            "Please use /newmatch inside your cricket group."
        )
        return

    pending_overs[
        (message.chat.id, message.from_user.id)
    ] = 0

    await message.answer(
        "🏆 CRICKET RIVALRY\n\nSelect match overs:",
        reply_markup=overs_kb()
    )


@router.callback_query(F.data.startswith("overs:"))
async def select_overs(call: CallbackQuery):

    overs = int(call.data.split(":")[1])

    pending_overs[
        (call.message.chat.id, call.from_user.id)
    ] = overs

    await call.message.edit_text(
        f"Selected {overs} overs.\n\nSelect wickets:",
        reply_markup=wickets_kb()
    )

    await call.answer()


@router.callback_query(F.data.startswith("wickets:"))
async def select_wickets(call: CallbackQuery):

    overs = pending_overs.get(
        (call.message.chat.id, call.from_user.id)
    )

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
            host_id=call.from_user.id,
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
        match.group_message_id = call.message.message_id

        await session.commit()

    pending_overs.pop(
        (call.message.chat.id, call.from_user.id),
        None
    )

    await call.message.edit_text(
        f"🏏 CRICKET RIVALRY #{match_id}\n"
        f"Host: {call.from_user.full_name}\n"
        f"Overs: {overs}\n"
        f"Wickets: {wickets}\n\n"
        "Select your team:",
        reply_markup=team_kb(match_id)
    )

    await call.answer("Match created!")


# ---------------- JOIN TEAM ----------------

@router.callback_query(F.data.startswith("join:"))
async def join_team(call: CallbackQuery):

    _, match_id, side = call.data.split(":")

    async with SessionLocal() as session:

        match = await session.get(Match, int(match_id))

        team = (await session.execute(
            select(Team).where(
                Team.match_id == int(match_id),
                Team.side == side
            )
        )).scalar_one_or_none()

        if not match or not team:
            await call.answer(
                "Match or team not found",
                show_alert=True
            )
            return

        existing = (await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.telegram_id == call.from_user.id
            )
        )).scalar_one_or_none()

        if existing:
            await call.answer(
                "Already joined!",
                show_alert=True
            )
            return

        session.add(TeamMember(
            team_id=team.id,
            telegram_id=call.from_user.id,
            display_name=call.from_user.full_name,
            is_captain=(
                team.captain_id == call.from_user.id
            )
        ))

        await session.commit()

    await call.answer(f"Joined Team {side}!")

    await call.message.answer(
        f"✅ {call.from_user.full_name} joined Team {side}"
    )


# ---------------- ADMIN PANEL ----------------

@router.message(Command("admin"))
async def admin_panel(message: Message):

    if message.chat.type == "private":
        await message.answer(
            "Use /admin inside your cricket group."
        )
        return

    async with SessionLocal() as session:

        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match.")
            return

        if not await is_host_or_admin(
            message.bot, match, message.from_user.id
        ):
            await message.answer(
                "Only Host / Group Admin"
            )
            return

        await message.answer(
            f"⚙️ ADMIN PANEL — Match #{match.id}",
            reply_markup=admin_kb(match.id)
        )


# ---------------- CAPTAIN PANEL ----------------

@router.message(Command("captainpanel"))
async def captain_panel(message: Message):

    async with SessionLocal() as session:

        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match.")
            return

        if not await is_host_or_captain(
            session, match, message.from_user.id
        ):
            await message.answer(
                "Only Host / Captain"
            )
            return

        teams = (await session.execute(
            select(Team).where(
                Team.match_id == match.id
            )
        )).scalars().all()

        await message.answer(
            "🏅 CAPTAIN CONTROL PANEL",
            reply_markup=captain_kb(match.id, teams)
        )


# ---------------- ADMIN BUTTON ACTIONS ----------------

@router.callback_query(F.data.startswith("admin:"))
async def admin_action(call: CallbackQuery):

    _, action, match_id = call.data.split(":")

    async with SessionLocal() as session:

        match = await session.get(Match, int(match_id))

        if not match:
            await call.answer(
                "Match not found",
                show_alert=True
            )
            return

        if action == "host":

            if not await require_host_or_admin(
                call, match
            ):
                return

            members = (await session.execute(
                select(TeamMember).join(Team).where(
                    Team.match_id == match.id
                )
            )).scalars().all()

            if not members:
                await call.answer(
                    "No joined players yet",
                    show_alert=True
                )
                return

            await call.message.edit_text(
                "👑 Choose the new host:",
                reply_markup=host_kb(match.id, members)
            )

        elif action == "captain":

            if not await require_host_or_captain(
                call, session, match
            ):
                return

            teams = (await session.execute(
                select(Team).where(
                    Team.match_id == match.id
                )
            )).scalars().all()

            await call.message.edit_text(
                "🏅 Choose a team to change its captain:",
                reply_markup=captain_kb(match.id, teams)
            )

        else:
            await call.answer(
                "Unknown admin action",
                show_alert=True
            )
            return

        await call.answer()


# ---------------- CHANGE HOST ----------------

@router.callback_query(F.data.startswith("hostset:"))
async def change_host(call: CallbackQuery):

    _, match_id, player_id = call.data.split(":")

    async with SessionLocal() as session:

        match = await session.get(Match, int(match_id))

        if not match:
            await call.answer(
                "Match not found",
                show_alert=True
            )
            return

        if not await require_host_or_admin(
            call, match
        ):
            return

        player = (await session.execute(
            select(TeamMember).join(Team).where(
                Team.match_id == match.id,
                TeamMember.telegram_id == int(player_id)
            )
        )).scalars().first()

        if not player:
            await call.answer(
                "Player not found",
                show_alert=True
            )
            return

        match.host_id = int(player_id)

        await session.commit()

    await call.message.edit_text(
        f"👑 Host changed to {player.display_name}"
    )

    await call.answer("Host changed!")


# ---------------- CHANGE CAPTAIN ----------------

@router.callback_query(F.data.startswith("captainteam:"))
async def choose_captain_team(call: CallbackQuery):

    _, match_id, team_id = call.data.split(":")

    async with SessionLocal() as session:

        match = await session.get(Match, int(match_id))

        if not match:
            await call.answer(
                "Match not found",
                show_alert=True
            )
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        players = (await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == int(team_id)
            )
        )).scalars().all()

        if not players:
            await call.answer(
                "No players in this team",
                show_alert=True
            )
            return

        await call.message.edit_text(
            "Select the new captain:",
            reply_markup=player_kb(
                players,
                f"captain:{match.id}:{team_id}"
            )
        )

    await call.answer()


@router.callback_query(F.data.startswith("captain:"))
async def set_captain(call: CallbackQuery):

    _, match_id, team_id, player_id = call.data.split(":")

    async with SessionLocal() as session:

        match = await session.get(Match, int(match_id))

        if not match:
            await call.answer(
                "Match not found",
                show_alert=True
            )
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        team = await session.get(Team, int(team_id))

        if not team or team.match_id != match.id:
            await call.answer(
                "Team not found",
                show_alert=True
            )
            return

        member = (await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id,
                TeamMember.telegram_id == int(player_id)
            )
        )).scalar_one_or_none()

        if not member:
            await call.answer(
                "Player/team not found",
                show_alert=True
            )
            return

        team.captain_id = int(player_id)

        all_members = (await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id
            )
        )).scalars().all()

        for item in all_members:
            item.is_captain = (
                item.telegram_id == int(player_id)
            )

        await session.commit()

        team_side = team.side
        player_name = member.display_name

    await call.message.edit_text(
        f"🏅 {player_name} is now captain of Team {team_side}"
    )

    await call.answer("Captain changed!")


# ---------------- SELECT BATSMAN ----------------

@router.message(Command("selectbatter"))
async def select_batter(message: Message):

    async with SessionLocal() as session:

        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match.")
            return

        if not await is_host_or_captain(
            session, match, message.from_user.id
        ):
            await message.answer(
                "Only Host / Captain"
            )
            return

        team = (await session.execute(
            select(Team).where(
                Team.match_id == match.id,
                Team.side == match.batting_side
            )
        )).scalar_one()

        players = (await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id
            )
        )).scalars().all()

        if not players:
            await message.answer("No batting players.")
            return

        await message.answer(
            "🏏 SELECT BATSMAN",
            reply_markup=player_kb(
                players, f"batter:{match.id}"
            )
        )


# ---------------- SELECT BOWLER ----------------

@router.message(Command("selectbowler"))
async def select_bowler(message: Message):

    async with SessionLocal() as session:

        match = await get_active_match(
            session, message.chat.id
        )

        if not match:
            await message.answer("No active match.")
            return

        if not await is_host_or_captain(
            session, match, message.from_user.id
        ):
            await message.answer(
                "Only Host / Captain"
            )
            return

        bowling_side = (
            "B" if match.batting_side == "A" else "A"
        )

        team = (await session.execute(
            select(Team).where(
                Team.match_id == match.id,
                Team.side == bowling_side
            )
        )).scalar_one()

        players = (await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team.id
            )
        )).scalars().all()

        if not players:
            await message.answer("No bowling players.")
            return

        await message.answer(
            "🎳 SELECT BOWLER",
            reply_markup=player_kb(
                players, f"bowler:{match.id}"
            )
        )


# ---------------- SET BATSMAN ----------------

@router.callback_query(F.data.startswith("batter:"))
async def set_batter(call: CallbackQuery):

    _, match_id, player_id = call.data.split(":")

    async with SessionLocal() as session:

        match = await session.get(Match, int(match_id))

        if not match:
            await call.answer(
                "Match not found",
                show_alert=True
            )
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        member = (await session.execute(
            select(TeamMember).join(Team).where(
                Team.match_id == match.id,
                TeamMember.telegram_id == int(player_id),
                Team.side == match.batting_side
            )
        )).scalars().first()

        if not member:
            await call.answer(
                "Choose a player from the batting team",
                show_alert=True
            )
            return

        match.striker_id = int(player_id)
        match.status = "live"

        await session.commit()

    await call.message.answer(
        f"🏏 Batsman selected: "
        f"<a href='tg://user?id={player_id}'>Player</a>",
        parse_mode="HTML"
    )

    await call.answer("Batsman selected!")


# ---------------- SET BOWLER ----------------

@router.callback_query(F.data.startswith("bowler:"))
async def set_bowler(call: CallbackQuery):

    _, match_id, player_id = call.data.split(":")

    async with SessionLocal() as session:

        match = await session.get(Match, int(match_id))

        if not match:
            await call.answer(
                "Match not found",
                show_alert=True
            )
            return

        if not await require_host_or_captain(
            call, session, match
        ):
            return

        if not match.striker_id:
            await call.answer(
                "Select a batsman first",
                show_alert=True
            )
            return

        bowling_side = (
            "B" if match.batting_side == "A" else "A"
        )

        member = (await session.execute(
            select(TeamMember).join(Team).where(
                Team.match_id == match.id,
                TeamMember.telegram_id == int(player_id),
                Team.side == bowling_side
            )
        )).scalars().first()

        if not member:
            await call.answer(
                "Choose a player from the bowling team",
                show_alert=True
            )
            return

        match.bowler_id = int(player_id)

        current_match_id = match.id
        runs = match.runs
        wickets = match.wickets
        balls = match.legal_balls
        batter_id = match.striker_id

        await session.commit()

    try:
        await call.bot.send_message(
            int(player_id),
            "🔔 YOUR BOWLING TURN!\n\n"
            f"Match: #{current_match_id}\n"
            f"Batsman: <a href='tg://user?id={batter_id}'>Batsman</a>\n"
            f"Score: {runs}/{wickets}\n"
            f"Overs: {balls // 6}.{balls % 6}",
            parse_mode="HTML",
            reply_markup=bowler_kb(current_match_id)
        )

    except Exception:
        await call.message.answer(
            "⚠️ Bowler must start the bot using /start "
            "before private notifications."
        )

    await call.message.answer(
        f"🎳 Bowler selected: "
        f"<a href='tg://user?id={player_id}'>Bowler</a>",
        parse_mode="HTML"
    )

    await call.answer("Bowler selected!")


# ---------------- BOWL NOW ----------------

@router.callback_query(F.data.startswith("bowl:"))
async def bowl_now(call: CallbackQuery):

    match_id = int(call.data.split(":")[1])

    async with SessionLocal() as session:

        match = await session.get(Match, match_id)

        if not match:
            await call.answer(
                "Match not found",
                show_alert=True
            )
            return

        if match.bowler_id != call.from_user.id:
            await call.answer(
                "Only the selected bowler",
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


# ---------------- SCORE BUTTONS ----------------

@router.callback_query(F.data.startswith("run:"))
async def add_runs(call: CallbackQuery):

    _, match_id, value = call.data.split(":")

    await update_score(
        call, int(match_id), int(value)
    )


@router.callback_query(F.data.startswith("wicket:"))
async def add_wicket(call: CallbackQuery):

    match_id = int(call.data.split(":")[1])

    await update_score(
        call, match_id, 0, wicket=True
    )


@router.callback_query(F.data.startswith("extra:"))
async def add_extra(call: CallbackQuery):

    _, match_id, extra = call.data.split(":")

    await update_score(
        call,
        int(match_id),
        1,
        extra=extra,
        legal=False
    )


# ---------------- UPDATE SCORE ----------------

async def update_score(
    call,
    match_id,
    runs,
    wicket=False,
    extra=None,
    legal=True
):

    celebrations = []

    async with SessionLocal() as session:

        match = await session.get(Match, match_id)

        if not match:
            await call.answer(
                "Match not found",
                show_alert=True
            )
            return

        if match.status != "live":
            await call.answer(
                "Match is not live",
                show_alert=True
            )
            return

        if match.bowler_id != call.from_user.id:
            await call.answer(
                "Only the selected bowler",
                show_alert=True
            )
            return

        old_batter_runs = match.batter_runs
        old_partnership = match.partnership_runs

        match.runs += runs

        if extra is None:
            match.batter_runs += runs

        match.partnership_runs += runs

        if runs == 4 and extra is None:
            celebrations.append("four")

        if runs == 6 and extra is None:
            celebrations.append("six")

        if old_batter_runs < 50 <= match.batter_runs:
            celebrations.append("fifty")

        if old_batter_runs < 100 <= match.batter_runs:
            celebrations.append("hundred")

        if old_partnership < 50 <= match.partnership_runs:
            celebrations.append("partnership_fifty")

        if old_partnership < 100 <= match.partnership_runs:
            celebrations.append("partnership_hundred")

        if wicket:
            match.wickets += 1
            match.partnership_runs = 0

        if legal:
            match.legal_balls += 1

        session.add(BallEvent(
            match_id=match_id,
            over_number=match.legal_balls // 6,
            ball_number=match.legal_balls % 6,
            batter_id=match.striker_id,
            bowler_id=match.bowler_id,
            runs=runs,
            extra_type=extra,
            wicket=wicket
        ))

        if (
            match.wickets >= match.wickets_limit
            or match.legal_balls >= match.overs * 6
        ):
            match.status = "innings_complete"

        score = f"{match.runs}/{match.wickets}"

        overs = (
            f"{match.legal_balls // 6}."
            f"{match.legal_balls % 6}"
        )

        complete = match.status == "innings_complete"

        await session.commit()

    await call.message.answer(
        f"🏏 CRICKET SCORE\n\n"
        f"Score: {score}\n"
        f"Overs: {overs}\n"
        f"Runs: {runs}\n"
        f"Wicket: {'YES' if wicket else 'NO'}"
        + (
            "\n🏆 INNINGS COMPLETED!"
            if complete else ""
        )
    )

    for event in celebrations:
        await send_event_media(
            call.bot,
            call.message.chat.id,
            event
        )

    await call.answer("Score updated!")
