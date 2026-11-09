from html import escape

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from access import clear_admin_cache
from db import is_group_chat, resolve_group, set_chat_group
from handlers.common import find_group_by_name, menu_markup, send_menu
from keyboards import get_main_menu
from texts import HELP_DM, HELP_GROUP, SHORT_MENU_DM

router = Router()


@router.message(Command("start", "help", "menu"))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    name = command.command  # start / help / menu

    if is_group_chat(message.chat):
        group = await resolve_group(message.from_user.id, message.chat)
        if name == "help" or not group:
            text = HELP_GROUP
            if not group:
                text += "\n\n⚠️ Цей чат ще не привʼязаний до групи."
            return await send_menu(message, bot, text)
        safe_name = escape(group["group_name"], quote=False)
        return await send_menu(
            message, bot,
            f"👋 <b>Бот розкладу КПІ</b> — {safe_name}\nОбери дію:",
            get_main_menu(group["group_id"], owner=message.from_user.id, in_group=True),
        )

    group = await resolve_group(message.from_user.id, message.chat)
    markup = await menu_markup(bot, message.from_user.id, group["group_id"] if group else None, 0, False)
    if name == "menu":
        return await message.reply(SHORT_MENU_DM, reply_markup=markup)
    await message.reply(HELP_DM, reply_markup=markup)


@router.message(Command("setgroup"))
async def cmd_setgroup(message: Message, command: CommandObject, bot: Bot):
    if not is_group_chat(message.chat):
        return await message.reply("Це команда для групових чатів. У ЛС скористайся меню «Задати групу».")

    anonymous_admin = message.sender_chat is not None and message.sender_chat.id == message.chat.id
    if not anonymous_admin:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("creator", "administrator"):
            return await message.reply("⛔ Групу чату може задати тільки адміністратор.")

    if not command.args:
        return await message.reply("Вкажи групу: <code>/setgroup ІЦ-12</code>")

    result, api_ok = await find_group_by_name(command.args)
    if not api_ok:
        return await message.reply("❌ API розкладу зараз недоступний, спробуй пізніше.")
    if not result:
        safe_input = escape(command.args, quote=False)
        return await message.reply(f"❌ Групу <b>{safe_input}</b> не знайдено.")

    set_by = message.from_user.id if message.from_user else 0
    await set_chat_group(message.chat.id, result["groupName"], result["id"], set_by)
    clear_admin_cache()
    safe_name = escape(result["groupName"], quote=False)
    await message.reply(f"✅ Чат привʼязано до групи <b>{safe_name}</b>. Відкрий меню: /menu")