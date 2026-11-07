import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import TOKEN
from db import init_db
from handlers import router
from live_views import live_view_updater


async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    asyncio.create_task(live_view_updater(bot))

    print("Бот запущений на aiogram v3 з підтримкою Rich Messages...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())