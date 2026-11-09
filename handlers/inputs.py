from contextlib import suppress
from html import escape
from urllib.parse import urlparse

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from access import is_group_admin
from callbacks import BotStates, MenuCB
from db import resolve_group, set_group, set_link
from handlers.common import find_group_by_name, menu_markup
from keyboards import get_cancel_menu

router = Router()


@router.message(StateFilter(BotStates.wait_group, BotStates.wait_link))
async def handle_inputs(message: Message, state: FSMContext, bot: Bot):
    current_state = await state.get_state()
    data = await state.get_data()
    msg_id = data.get("msg_id")

    with suppress(TelegramBadRequest):
        await message.delete()

    if not message.text:
        with suppress(TelegramBadRequest):
            await bot.edit_message_text(
                "❌ Будь ласка, надішли текстом",
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=get_cancel_menu()
            )
        return

    if current_state == BotStates.wait_group:
        result, api_ok = await find_group_by_name(message.text)

        if result:
            await set_group(message.from_user.id, result["groupName"], result["id"])
            await state.clear()
            safe_group_name = escape(result["groupName"], quote=False)
            with suppress(TelegramBadRequest):
                await bot.edit_message_text(f"✅ Група <b>{safe_group_name}</b> збережена!", chat_id=message.chat.id,
                                            message_id=msg_id,
                                            reply_markup=await menu_markup(bot, message.from_user.id, result["id"], 0, False))
        else:
            safe_input = escape(message.text, quote=False)
            text = (f"❌ Групу <b>{safe_input}</b> не знайдено. Спробуй ще раз:" if api_ok
                    else "❌ API розкладу зараз недоступний. Спробуй ще раз трохи пізніше:")
            with suppress(TelegramBadRequest):
                await bot.edit_message_text(text, chat_id=message.chat.id, message_id=msg_id,
                                            reply_markup=get_cancel_menu())

    elif current_state == BotStates.wait_link:
        group = await resolve_group(message.from_user.id, message.chat)
        if not group:
            await state.clear()
            builder = InlineKeyboardBuilder()
            builder.button(text="🏠 Головне меню", callback_data=MenuCB(action="main"))

            with suppress(TelegramBadRequest):
                await bot.edit_message_text(
                    "❌ Спочатку задай групу!",
                    chat_id=message.chat.id,
                    message_id=msg_id,
                    reply_markup=builder.as_markup()
                )
            return

        text = message.text.strip()
        parsed = urlparse(text)

        is_valid = text == "-" or (parsed.scheme in ("http", "https") and bool(parsed.netloc))

        if not is_valid:
            with suppress(TelegramBadRequest):
                await bot.edit_message_text(
                    "❌ Некоректний формат! Надішли дійсне посилання (http/https) або дефіс (-) для видалення:",
                    chat_id=message.chat.id,
                    message_id=msg_id,
                    reply_markup=get_cancel_menu()
                )
            return

        subject, pair_type = data["subject"], data["pair_type"]
        shared = bool(data.get("shared"))

        if shared and not await is_group_admin(bot, message.from_user.id, group["group_id"], force=True):
            await state.clear()
            with suppress(TelegramBadRequest):
                await bot.edit_message_text(
                    "⛔ Спільні лінки може задавати тільки адмін чату.",
                    chat_id=message.chat.id,
                    message_id=msg_id,
                    reply_markup=await menu_markup(bot, message.from_user.id, group["group_id"], 0, False),
                )
            return

        await set_link(message.from_user.id, group["group_id"], subject, pair_type, text, shared=shared)
        await state.clear()

        builder = InlineKeyboardBuilder()
        builder.button(text="🏠 Головне меню", callback_data=MenuCB(action="main"))
        response_text = "❌ Посилання видалено!" if text == "-" else "✅ Посилання збережено!"

        with suppress(TelegramBadRequest):
            await bot.edit_message_text(
                response_text,
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=builder.as_markup()
            )