from contextlib import suppress
from html import escape
import zlib

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from access import is_group_admin
from callbacks import BotStates, LinkSubjCB, LinkTypeCB, MenuCB
from config import TYPE_ICONS
from db import get_link, resolve_group
from formatting import get_subject_by_id
from handlers.common import dm_only, edit_screen, link_subjects, no_group_text
from keyboards import get_cancel_menu
from live_views import untrack_live_view

router = Router()


@router.callback_query(LinkSubjCB.filter(F.idx == -1))
async def cb_link_subjects_list(query: CallbackQuery, callback_data: LinkSubjCB, bot: Bot):
    if await dm_only(query):
        return
    untrack_live_view(query.message.chat.id)
    group = await resolve_group(query.from_user.id, query.message.chat)
    if not group:
        return await query.answer(no_group_text(False), show_alert=True)

    shared = bool(callback_data.shared)
    if shared and not await is_group_admin(bot, query.from_user.id, group["group_id"]):
        return await query.answer(
            "Спільні лінки може задавати тільки адмін чату, привʼязаного до твоєї групи.", show_alert=True
        )

    subjects = await link_subjects(query.from_user.id, group["group_id"], shared)
    if not subjects:
        return await query.answer(
            "Усі предмети приховані. Зайди в «Мої предмети», щоб щось увімкнути.", show_alert=True
        )

    page = callback_data.page
    PAGE_SIZE = 7
    start = page * PAGE_SIZE
    chunk = subjects[start:start + PAGE_SIZE]
    sh = int(shared)

    builder = InlineKeyboardBuilder()
    for s in chunk:
        subj_id = zlib.crc32(s.encode())
        builder.button(text=s[:35], callback_data=LinkSubjCB(page=page, idx=subj_id, shared=sh))
    builder.adjust(1)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️", callback_data=LinkSubjCB(page=page - 1, idx=-1, shared=sh).pack()))
    nav_buttons.append(InlineKeyboardButton(text=f"Стор. {page + 1}", callback_data="noop"))
    if start + PAGE_SIZE < len(subjects):
        nav_buttons.append(InlineKeyboardButton(
            text="➡️", callback_data=LinkSubjCB(page=page + 1, idx=-1, shared=sh).pack()))

    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="🏠 Головне меню", callback_data=MenuCB(action="main").pack()))

    if shared:
        title = ("👥 <b>Спільні лінки групи</b>\n"
                 "Їх бачать усі в чаті, у кого немає особистого лінка на цей предмет.\n"
                 "Обери предмет:")
    else:
        title = ("🔗 Обери предмет для налаштування посилання:\n"
                 "<i>(показані лише ті, що активні в «Моїх предметах»)</i>")

    with suppress(TelegramBadRequest):
        await edit_screen(query, bot, title, reply_markup=builder.as_markup())
    await query.answer()


@router.callback_query(LinkSubjCB.filter(F.idx >= 0))
async def cb_link_subject_detail(query: CallbackQuery, callback_data: LinkSubjCB, bot: Bot):
    if await dm_only(query):
        return
    group = await resolve_group(query.from_user.id, query.message.chat)
    if not group:
        return await query.answer(no_group_text(False), show_alert=True)

    shared = bool(callback_data.shared)
    if shared and not await is_group_admin(bot, query.from_user.id, group["group_id"]):
        return await query.answer("Спільні лінки може задавати тільки адмін чату.", show_alert=True)

    subjects = await link_subjects(query.from_user.id, group["group_id"], shared)
    subject = get_subject_by_id(subjects, callback_data.idx)
    if not subject:
        return await query.answer("Список змінився, відкрий ще раз", show_alert=True)

    safe_subject = escape(subject, quote=False)
    owner_id = 0 if shared else query.from_user.id
    sh = int(shared)

    builder = InlineKeyboardBuilder()
    for p_type, icon in TYPE_ICONS.items():
        exists = await get_link(owner_id, group["group_id"], subject, p_type)
        mark = "✅" if exists else "➕"
        builder.button(text=f"{icon} {p_type} {mark}",
                       callback_data=LinkTypeCB(idx=callback_data.idx, pair_type=p_type, shared=sh))

    builder.button(text="⬅️ Назад до списку",
                   callback_data=LinkSubjCB(page=callback_data.page, idx=-1, shared=sh))
    builder.adjust(1)

    prefix = "👥 " if shared else "📚 "
    with suppress(TelegramBadRequest):
        await edit_screen(query, bot, f"{prefix}<b>{safe_subject}</b>\nОбери тип заняття:",
                          reply_markup=builder.as_markup())
    await query.answer()


@router.callback_query(LinkTypeCB.filter())
async def cb_link_edit(query: CallbackQuery, callback_data: LinkTypeCB, state: FSMContext, bot: Bot):
    if await dm_only(query):
        return
    group = await resolve_group(query.from_user.id, query.message.chat)
    if not group:
        return await query.answer(no_group_text(False), show_alert=True)

    shared = bool(callback_data.shared)
    if shared and not await is_group_admin(bot, query.from_user.id, group["group_id"]):
        return await query.answer("Спільні лінки може задавати тільки адмін чату.", show_alert=True)

    subjects = await link_subjects(query.from_user.id, group["group_id"], shared)
    subject = get_subject_by_id(subjects, callback_data.idx)
    if not subject:
        return await query.answer("Список змінився, відкрий ще раз", show_alert=True)

    owner_id = 0 if shared else query.from_user.id
    link = await get_link(owner_id, group["group_id"], subject, callback_data.pair_type)

    await state.set_state(BotStates.wait_link)
    await state.update_data(subject=subject, pair_type=callback_data.pair_type,
                            msg_id=query.message.message_id, shared=shared)

    safe_subject = escape(subject, quote=False)
    safe_link = escape(link, quote=False) if link else None
    kind = "👥 Спільне посилання" if shared else "🔗"
    head = f"{kind} <b>{safe_subject}</b> ({callback_data.pair_type})"

    text = (f"{head}\n\nПоточне: <code>{safe_link}</code>\n\n"
            f"Надішли нове посилання або <code>-</code> щоб видалити."
            if link else
            f"{head}\n\nПосилання не задано. Надішли його повідомленням.")

    with suppress(TelegramBadRequest):
        await edit_screen(query, bot, text, reply_markup=get_cancel_menu())
    await query.answer()