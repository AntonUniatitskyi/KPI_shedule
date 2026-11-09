"""Сповіщення власника бота в Telegram (помилки, запуск) з обмеженням частоти."""
import logging
import time
import traceback
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from config import ADMIN_ID

DEFAULT_COOLDOWN = 600  # однакову помилку надсилаємо не частіше, ніж раз на 10 хв

_last_sent: dict[str, float] = {}
_suppressed: dict[str, int] = {}


def error_location(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames if "site-packages" not in f.filename]
    frame = (ours or frames or [None])[-1]
    if frame is None:
        return "невідомо"
    parts = frame.filename.replace("\\", "/").split("/")
    return f"{'/'.join(parts[-2:])}:{frame.lineno} ({frame.name})"


def format_error(exc: BaseException, update_info: str = "") -> str:
    message = escape(f"{type(exc).__name__}: {exc}"[:400], quote=False)
    text = f"⚠️ <b>Помилка бота</b>\n<code>{message}</code>\n📍 {escape(error_location(exc), quote=False)}"
    if update_info:
        text += f"\n👤 {escape(update_info, quote=False)}"
    return text


async def notify_admin(bot: Bot, text: str, key: str | None = None, cooldown: float = DEFAULT_COOLDOWN) -> bool:
    if not ADMIN_ID:
        return False

    now = time.monotonic()
    if key is not None and cooldown > 0:
        last = _last_sent.get(key)
        if last is not None and now - last < cooldown:
            _suppressed[key] = _suppressed.get(key, 0) + 1
            return False
        skipped = _suppressed.pop(key, 0)
        if skipped:
            text += f"\n(+{skipped} таких самих за цей час)"
        _last_sent[key] = now

    try:
        await bot.send_message(ADMIN_ID, text)
        return True
    except TelegramAPIError as e:
        logging.warning("Не вдалось надіслати сповіщення власнику: %s", e)
        return False