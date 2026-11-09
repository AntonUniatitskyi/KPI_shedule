import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from db import get_chats_for_group

POSITIVE_TTL = 600   # адмін — перевіряємо раз на 10 хв
NEGATIVE_TTL = 120   # не адмін — трохи частіше, щоб нові права підхоплювались швидко

_CACHE: dict[tuple[int, int], tuple[bool, float]] = {}


def clear_admin_cache():
    _CACHE.clear()


def cached_is_admin(user_id: int, group_id: int) -> bool:
    entry = _CACHE.get((user_id, group_id))
    return bool(entry and entry[1] > time.monotonic() and entry[0])


async def is_group_admin(bot: Bot, user_id: int, group_id: int, force: bool = False) -> bool:
    key = (user_id, group_id)
    entry = _CACHE.get(key)
    if not force and entry and entry[1] > time.monotonic():
        return entry[0]

    result = False
    for chat_id in await get_chats_for_group(group_id):
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except TelegramAPIError:
            continue  # бота прибрали з чату або чат недоступний
        if member.status in ("creator", "administrator"):
            result = True
            break

    ttl = POSITIVE_TTL if result else NEGATIVE_TTL
    _CACHE[key] = (result, time.monotonic() + ttl)
    return result