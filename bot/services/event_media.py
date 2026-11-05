from bot.config import settings


EVENTS = {
    "four": (
        settings.four_gif_url,
        settings.four_mp3_url,
        "💥 FOUR!"
    ),

    "six": (
        settings.six_gif_url,
        settings.six_mp3_url,
        "🚀 SIX! WHAT A SHOT!"
    ),

    "fifty": (
        settings.fifty_gif_url,
        settings.fifty_mp3_url,
        "🏅 HALF CENTURY!"
    ),

    "hundred": (
        settings.hundred_gif_url,
        settings.hundred_mp3_url,
        "💯 CENTURY!"
    ),

    "partnership_fifty": (
        settings.partnership_fifty_gif_url,
        settings.partnership_fifty_mp3_url,
        "🤝 50 RUN PARTNERSHIP!"
    ),

    "partnership_hundred": (
        settings.partnership_hundred_gif_url,
        settings.partnership_hundred_mp3_url,
        "🔥 100 RUN PARTNERSHIP!"
    )
}


async def send_event_media(bot, chat_id, event):

    gif, mp3, caption = EVENTS[event]

    if gif:
        try:
            await bot.send_animation(
                chat_id=chat_id,
                animation=gif,
                caption=caption
            )
        except Exception:
            await bot.send_message(
                chat_id,
                caption + "\nAnimation could not be sent."
            )
    else:
        await bot.send_message(chat_id, caption)

    if mp3:
        try:
            await bot.send_audio(
                chat_id=chat_id,
                audio=mp3
            )
        except Exception:
            await bot.send_message(
                chat_id,
                "⚠️ MP3 could not be sent. Check media settings."
            )
