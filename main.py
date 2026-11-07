import asyncio
import logging

from api import close_session

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TOKEN
from db import init_db
from handlers import router
from live_views import live_view_updater

background_tasks = set()
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
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