import logging
import time
from collections import deque

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ErrorEvent

from notifier import error_location, format_error, notify_admin

router = Router()

ERROR_TIMES: deque[float] = deque(maxlen=2000)

_QUIET_BAD_REQUESTS = ("query is too old", "message is not modified", "message to edit not found")


def _is_quiet(exc: BaseException) -> bool:
    if isinstance(exc, TelegramForbiddenError):  # користувач заблокував бота
        return True
    if isinstance(exc, TelegramBadRequest):
        return any(s in str(exc) for s in _QUIET_BAD_REQUESTS)
    return False


def _update_info(event: ErrorEvent) -> str:
    try:
        update = event.update
        kind = update.event_type
        user = getattr(getattr(update, kind, None), "from_user", None)
        return f"user {user.id} · {kind}" if user else kind
    except Exception:
        return ""


@router.error()
async def on_error(event: ErrorEvent, bot: Bot):
    exc = event.exception
    if _is_quiet(exc):
        logging.warning("Очікувана помилка Telegram: %s", exc)
        return True

    ERROR_TIMES.append(time.time())
    logging.error("Необроблена помилка в хендлері", exc_info=exc)
    key = f"{type(exc).__name__}@{error_location(exc)}"
    await notify_admin(bot, format_error(exc, _update_info(event)), key=key)
    return True