import asyncio
import logging
import os
import time

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from api import close_session, set_alert_handler
from config import TOKEN
from db import init_db, load_live_views, save_live_views
from handlers import router
from live_views import LIVE_VIEWS, live_view_updater
from notifier import notify_admin

background_tasks: set[asyncio.Task] = set()

STARTUP_MARK = os.path.join("data", ".last_start")
STARTUP_QUIET = 600  # не чаще раза в 10 мин


def should_notify_startup() -> bool:
    try:
        recent = time.time() - os.path.getmtime(STARTUP_MARK) < STARTUP_QUIET
    except OSError:
        recent = False
    with open(STARTUP_MARK, "w"):
        pass
    return not recent


async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    LIVE_VIEWS.update(await load_live_views())
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Інструкція та меню"),
            BotCommand(command="menu", description="Головне меню"),
            BotCommand(command="help", description="Як користуватись ботом"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="menu", description="Відкрити меню розкладу (бачиш тільки ти)",
                           is_ephemeral=True),
                BotCommand(command="help", description="Як користуватись ботом", is_ephemeral=True),
                BotCommand(command="setgroup", description="Адмін: задати групу чату, напр. /setgroup ІЦ-12"),
            ],
            scope=BotCommandScopeAllGroupChats(),
        )
    except Exception:
        logging.exception("Не вдалось зареєструвати ephemeral-команди для груп")
    dp = Dispatcher()
    dp.include_router(router)

    # ключ зависит от первого символа (🔴 / ✅), чтобы «знову працює» не глушилось кулдауном «лежить»
    set_alert_handler(lambda text: notify_admin(bot, text, key=f"api:{text[:1]}", cooldown=900))

    task = asyncio.create_task(live_view_updater(bot))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    print("Бот запущений на aiogram v3 з підтримкою Rich Messages...")
    if should_notify_startup():
        await notify_admin(bot, "🟢 Бот запущено")
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        try:
            await save_live_views(LIVE_VIEWS)
        except Exception:
            logging.exception("Не вдалось зберегти live views при зупинці")
        await close_session()


if __name__ == "__main__":
    asyncio.run(main())