import asyncio
import logging
from contextlib import suppress
from datetime import datetime, time as dtime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import LinkPreviewOptions

from api import get_schedule
from config import KPI_BELLS
from formatting import format_day, format_week, get_week_type
from keyboards import get_main_menu, week_nav_keyboard

LIVE_VIEWS: dict[int, dict] = {}


def track_live_view(chat_id: int, message_id: int, kind: str, group_id: int, user_id: int):
    LIVE_VIEWS[chat_id] = {
        "message_id": message_id, "kind": kind, "group_id": group_id, "user_id": user_id,
    }


def untrack_live_view(chat_id: int):
    LIVE_VIEWS.pop(chat_id, None)


def next_wake_time(now: datetime) -> datetime:
    candidates = []
    for start, end, _ in KPI_BELLS:
        for t in (start, end):
            dt = datetime.combine(now.date(), t)
            if dt > now:
                candidates.append(dt)
    candidates.append(datetime.combine(now.date() + timedelta(days=1), dtime(0, 0)))
    return min(candidates)


async def live_view_updater(bot: Bot):
    while True:
        now = datetime.now()
        wake_at = next_wake_time(now)
        await asyncio.sleep(max((wake_at - now).total_seconds(), 5))
        try:
            await _refresh_all_live_views(bot)
        except Exception:
            logging.exception("live_view_updater: цикл оновлення впав, продовжуємо далі")


async def _refresh_all_live_views(bot: Bot):
        for chat_id, info in list(LIVE_VIEWS.items()):
            schedule = await get_schedule(info["group_id"])
            if not schedule:
                continue

            now = datetime.now()
            if info["kind"] == "today":
                rich_msg = await format_day(schedule, now, info["group_id"], info["user_id"])
                markup = get_main_menu(info["group_id"])
            else:  # week_current
                rich_msg = await format_week(schedule, now, info["group_id"], info["user_id"])
                wt = "first" if get_week_type(now) == "scheduleFirstWeek" else "second"
                markup = week_nav_keyboard(wt)

            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=info["message_id"],
                    text="Твій розклад (Rich Messages не підтримуються клієнтом)",
                    rich_message=rich_msg,
                    reply_markup=markup,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            except TelegramBadRequest:
                untrack_live_view(chat_id)
