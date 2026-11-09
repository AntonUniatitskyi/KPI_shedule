import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, EphemeralMessageParameters, InlineKeyboardMarkup, Message

from access import is_group_admin
from api import api_get_all_groups, get_all_group_subjects
from db import is_group_chat
from formatting import get_visible_subjects, normalize_group_name
from keyboards import get_main_menu


def no_group_text(in_group: bool) -> str:
    if in_group:
        return "Цей чат ще не привʼязаний до групи. Адмін має виконати /setgroup ІЦ-12"
    return "Спочатку задай групу!"


async def edit_screen(query: CallbackQuery, bot: Bot, text: str, *, rich_message=None,
                      reply_markup: InlineKeyboardMarkup | None = None, link_preview_options=None):
    msg = query.message
    kwargs = {"reply_markup": reply_markup}
    if rich_message is not None:
        kwargs["rich_message"] = rich_message
    if link_preview_options is not None:
        kwargs["link_preview_options"] = link_preview_options

    eph_id = getattr(msg, "ephemeral_message_id", None)
    if eph_id:
        await bot.edit_ephemeral_message_text(
            chat_id=msg.chat.id,
            receiver_user_id=query.from_user.id,
            ephemeral_message_id=eph_id,
            text=text,
            **kwargs,
        )
    else:
        await msg.edit_text(text, **kwargs)


async def send_menu(message: Message, bot: Bot, text: str, reply_markup: InlineKeyboardMarkup | None = None):
    if is_group_chat(message.chat) and message.from_user:
        try:
            await bot.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=reply_markup,
                ephemeral_message_parameters=EphemeralMessageParameters(
                    receiver_user_id=message.from_user.id
                ),
            )
            return
        except TelegramBadRequest as e:
            logging.warning("Ephemeral-відповідь не вдалась, надсилаю звичайну: %s", e)
    await message.reply(text, reply_markup=reply_markup)


async def menu_markup(bot: Bot, user_id: int, group_id: int | None, owner: int, in_group: bool):
    show_shared = bool(group_id) and not in_group and await is_group_admin(bot, user_id, group_id)
    return get_main_menu(group_id, owner, in_group, show_shared)


async def link_subjects(user_id: int, group_id: int, shared: bool) -> list[str]:
    if shared:
        return await get_all_group_subjects(group_id)
    return await get_visible_subjects(user_id, group_id)


async def deny_foreign(query: CallbackQuery, callback_data) -> bool:
    owner = getattr(callback_data, "owner", 0)
    if owner and owner != query.from_user.id:
        await query.answer("Це меню іншого користувача. Відкрий своє: /menu", show_alert=True)
        return True
    return False


async def dm_only(query: CallbackQuery) -> bool:
    if is_group_chat(query.message.chat):
        await query.answer("Це налаштовується в особистих повідомленнях з ботом.", show_alert=True)
        return True
    return False


async def find_group_by_name(text: str):
    groups = await api_get_all_groups()
    if not groups:
        return None, False
    norm_text = normalize_group_name(text)
    result = next((g for g in groups if normalize_group_name(g["groupName"]) == norm_text), None)
    return result, True