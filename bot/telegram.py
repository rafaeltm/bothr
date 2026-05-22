from __future__ import annotations

from telegram import Bot

import config

_bot_token: str | None = None
bot: Bot | None = None


def refresh_bot() -> Bot | None:
    global bot, _bot_token
    if config.BOT_TOKEN != _bot_token:
        _bot_token = config.BOT_TOKEN
        bot = Bot(token=_bot_token) if _bot_token else None
    return bot


async def send_message(chat_id: str | None, text: str) -> None:
    current_bot = refresh_bot()
    if not current_bot or not chat_id:
        return
    await current_bot.send_message(chat_id=chat_id, text=text)


refresh_bot()
