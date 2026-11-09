from contextlib import suppress
import zlib

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api import get_all_group_subjects
from callbacks import FilterCB, MenuCB
from db import get_hidden_subjects, is_group_chat, resolve_group, toggle_hidden_subject
from formatting import get_subject_by_id
from handlers.common import deny_foreign, edit_screen, no_group_text
from live_views import untrack_live_view

router = Router()


@router.callback_query(FilterCB.filter())
async def cb_filter_subjects(query: CallbackQuery, callback_data: FilterCB, bot: Bot):
    if await deny_foreign(query, callback_data):
        return
    untrack_live_view(query.message.chat.id)
    owner = callback_data.owner
    in_group = is_group_chat(query.message.chat)
    group = await resolve_group(query.from_user.id, query.message.chat)
    if not group:
        return await query.answer(no_group_text(in_group), show_alert=True)

    subjects = await get_all_group_subjects(group["group_id"])
    if not subjects:
        return await query.answer("❌ Не знайдено предметів")

    page = callback_data.page
    PAGE_SIZE = 7

    if callback_data.action == "toggle":
        subj_name = get_subject_by_id(subjects, callback_data.idx)
        if not subj_name:
            return await query.answer("Список змінився, відкрий ще раз", show_alert=True)
        is_now_hidden = await toggle_hidden_subject(query.from_user.id, group["group_id"], subj_name)
        status_msg = "❌ Приховано з розкладу" if is_now_hidden else "✅ Додано в розклад"
        await query.answer(status_msg)

    hidden = await get_hidden_subjects(query.from_user.id, group["group_id"])
    start = page * PAGE_SIZE
    chunk = subjects[start:start + PAGE_SIZE]

    builder = InlineKeyboardBuilder()
    for s in chunk:
        subj_id = zlib.crc32(s.encode())
        mark = "❌" if s in hidden else "✅"
        btn_text = f"{mark} {s[:32]}..." if len(s) > 35 else f"{mark} {s}"
        builder.button(text=btn_text, callback_data=FilterCB(action="toggle", page=page, idx=subj_id, owner=owner))

    builder.adjust(1)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️", callback_data=FilterCB(action="list", page=page - 1, owner=owner).pack()))
    nav_buttons.append(
        InlineKeyboardButton(text=f"Стор. {page + 1}/{(len(subjects) - 1) // PAGE_SIZE + 1}", callback_data="noop"))
    if start + PAGE_SIZE < len(subjects):
        nav_buttons.append(InlineKeyboardButton(
            text="➡️", callback_data=FilterCB(action="list", page=page + 1, owner=owner).pack()))

    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="🏠 Головне меню", callback_data=MenuCB(action="main", owner=owner).pack()))

    text = (
        "🎯 <b>Налаштування твоїх предметів</b>\n\n"
        "Натискай на назву, щоб приховати або повернути предмет у розклад:\n"
        "✅ — відображається у розкладі\n"
        "❌ — приховано (вибіркова, яку ти не відвідуєш)"
    )

    with suppress(TelegramBadRequest):
        await edit_screen(query, bot, text, reply_markup=builder.as_markup())
    if callback_data.action != "toggle":
        await query.answer()