from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


def overs_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{v} Overs",
                    callback_data=f"overs:{v}"
                )
                for v in [2, 5, 10]
            ],
            [
                InlineKeyboardButton(
                    text=f"{v} Overs",
                    callback_data=f"overs:{v}"
                )
                for v in [15, 20, 50]
            ]
        ]
    )


def wickets_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{v} Wickets",
                    callback_data=f"wickets:{v}"
                )
                for v in [1, 2]
            ],
            [
                InlineKeyboardButton(
                    text=f"{v} Wickets",
                    callback_data=f"wickets:{v}"
                )
                for v in [5, 10]
            ]
        ]
    )


def team_kb(match_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔴 Join Team A",
                    callback_data=f"join:{match_id}:A"
                ),
                InlineKeyboardButton(
                    text="🔵 Join Team B",
                    callback_data=f"join:{match_id}:B"
                )
            ]
        ]
    )


def player_kb(players, prefix):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=p.display_name,
                    callback_data=f"{prefix}:{p.telegram_id}"
                )
            ]
            for p in players
        ]
    )


def bowler_kb(match_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎳 BOWL NOW",
                    callback_data=f"bowl:{match_id}"
                )
            ]
        ]
    )


def score_kb(match_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=str(r),
                    callback_data=f"run:{match_id}:{r}"
                )
                for r in [0, 1, 2, 3, 4, 6]
            ],
            [
                InlineKeyboardButton(
                    text="❌ WICKET",
                    callback_data=f"wicket:{match_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="WIDE",
                    callback_data=f"extra:{match_id}:wide"
                ),
                InlineKeyboardButton(
                    text="NO BALL",
                    callback_data=f"extra:{match_id}:noball"
                )
            ]
        ]
    )
