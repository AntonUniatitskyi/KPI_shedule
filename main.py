import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from api import close_session
from config import TOKEN
from db import init_db
from handlers import router
from live_views import live_view_updater

background_tasks: set[asyncio.Task] = set()


async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
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

    task = asyncio.create_task(live_view_updater(bot))
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    print("Бот запущений на aiogram v3 з підтримкою Rich Messages...")
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await close_session()


if __name__ == "__main__":
    asyncio.run(main())