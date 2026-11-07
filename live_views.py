import asyncio
import logging
from datetime import datetime, time as dtime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import LinkPreviewOptions

from api import get_schedule
from config import KPI_BELLS, now_kyiv, TZ
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
            dt = datetime.combine(now.date(), t, tzinfo=TZ)
            if dt > now:
                candidates.append(dt)
    candidates.append(datetime.combine(now.date() + timedelta(days=1), dtime(0, 0), tzinfo=TZ))
    return min(candidates)


async def live_view_updater(bot: Bot):
    while True:
        now = now_kyiv()
        wake_at = next_wake_time(now)
        await asyncio.sleep(max((wake_at - now).total_seconds(), 5))
        try:
            await _refresh_all_live_views(bot)
        except Exception:
            logging.exception("live_view_updater: цикл оновлення впав, продовжуємо далі")


async def _refresh_all_live_views(bot: Bot):
    for chat_id, info in list(LIVE_VIEWS.items()):
        try:
            schedule = await get_schedule(info["group_id"])
            if not schedule:
                continue

            now = now_kyiv()
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
            except TelegramRetryAfter as e:
                logging.warning(f"Rate limit: чекаємо {e.retry_after} секунд...")
                await asyncio.sleep(e.retry_after)
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=info["message_id"],
                    text="Твій розклад (Rich Messages не підтримуються клієнтом)",
                    rich_message=rich_msg,
                    reply_markup=markup,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
        except TelegramForbiddenError:
            logging.info(f"Користувач {chat_id} заблокував бота. Відв'язуємо live view.")
            untrack_live_view(chat_id)
        except TelegramBadRequest as e:
            if "message is not modified" in e.message:
                pass
            elif "message to edit not found" in e.message or "message can't be edited" in e.message:
                untrack_live_view(chat_id)
            else:
                logging.exception(f"Неочікуваний BadRequest для {chat_id}: {e.message}")
        except Exception:
            logging.exception(f"Помилка оновлення live view для {chat_id}")
        await asyncio.sleep(0.1)
