from contextlib import suppress
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMemberUpdated, Message

from access import clear_admin_cache
from db import delete_chat_group, is_group_chat, migrate_chat_group
from texts import HELP_GROUP

router = Router()


@router.my_chat_member()
async def on_bot_membership_changed(event: ChatMemberUpdated, bot: Bot):
    if not is_group_chat(event.chat):
        return
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    if new_status in ("left", "kicked"):
        await delete_chat_group(event.chat.id)
        clear_admin_cache()
        logging.info("Бота прибрали з чату %s — привʼязку до групи видалено", event.chat.id)
    elif old_status in ("left", "kicked") and new_status in ("member", "administrator"):
        with suppress(TelegramBadRequest):
            await bot.send_message(
                event.chat.id,
                HELP_GROUP + "\n\n⚠️ Цей чат ще не привʼязаний до групи. "
                             "Адмін має виконати <code>/setgroup ІЦ-12</code>.",
            )


@router.message(F.migrate_to_chat_id)
async def on_chat_migrated(message: Message):
    await migrate_chat_group(message.chat.id, message.migrate_to_chat_id)
    clear_admin_cache()
    logging.info("Чат %s став супергрупою %s — привʼязку перенесено", message.chat.id, message.migrate_to_chat_id)