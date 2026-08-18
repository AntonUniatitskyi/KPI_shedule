from contextlib import suppress
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InputRichBlockParagraph,
    InputRichMessage,
    LinkPreviewOptions,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api import api_get_all_groups, get_all_group_subjects, get_schedule
from callbacks import BotStates, DayCB, FilterCB, LinkSubjCB, LinkTypeCB, MenuCB, WeekCB
from config import TYPE_ICONS
from db import get_group, get_hidden_subjects, get_link, set_group, set_link, toggle_hidden_subject
from formatting import format_day, format_week, get_visible_subjects, get_week_type, get_what_now
from keyboards import LAST_REFRESH, get_cancel_menu, get_main_menu, week_nav_keyboard
from live_views import track_live_view, untrack_live_view


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.reply("👋 *Бот розкладу КПІ*\n\nОбери дію:", parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_main_menu())


@router.callback_query(MenuCB.filter(F.action == "main"))
async def cb_main_menu(query: CallbackQuery, state: FSMContext):
    untrack_live_view(query.message.chat.id)
    await state.clear()
    group = await get_group(query.from_user.id)
    with suppress(TelegramBadRequest):
        await query.message.edit_text("🏠 *Головне меню*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_menu(group["group_id"] if group else None))
    await query.answer()


@router.callback_query(MenuCB.filter(F.action == "set_group"))
async def cb_set_group(query: CallbackQuery, state: FSMContext):
    untrack_live_view(query.message.chat.id)
    await state.set_state(BotStates.wait_group)
    await state.update_data(msg_id=query.message.message_id)
    with suppress(TelegramBadRequest):
        await query.message.edit_text("Введи точну назву групи (наприклад, ІЦ-12):", reply_markup=get_cancel_menu())
    await query.answer()


@router.callback_query(MenuCB.filter(F.action == "refresh"))
async def cb_refresh(query: CallbackQuery):
    group = await get_group(query.from_user.id)
    if not group: return await query.answer("Спочатку задай групу!", show_alert=True)

    await get_schedule(group["group_id"], force=True)
    LAST_REFRESH[group["group_id"]] = datetime.now()
    now_str = datetime.now().strftime("%H:%M:%S")
    await query.answer("✅ Оновлено!")

    with suppress(TelegramBadRequest):
        await query.message.edit_text(f"🏠 *Головне меню*\n_🔄 Оновлено о {now_str}_", parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=get_main_menu(group["group_id"]))


@router.callback_query(MenuCB.filter(F.action == "now"))
async def cb_what_now(query: CallbackQuery):
    untrack_live_view(query.message.chat.id)
    group = await get_group(query.from_user.id)
    if not group: return await query.answer("Спочатку задай групу!", show_alert=True)

    schedule = await get_schedule(group["group_id"])

    if schedule:
        rich_msg = await get_what_now(schedule, datetime.now(), group["group_id"], query.from_user.id)
    else:
        rich_msg = InputRichMessage(blocks=[InputRichBlockParagraph(text="❌ Помилка API")])

    with suppress(TelegramBadRequest):
        await query.message.edit_text(
            text="Твій розклад (Rich Messages не підтримуються клієнтом)",
            rich_message=rich_msg,
            reply_markup=get_main_menu(group["group_id"]),
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
    await query.answer()


@router.callback_query(DayCB.filter())
async def cb_day(query: CallbackQuery, callback_data: DayCB):
    group = await get_group(query.from_user.id)
    if not group: return await query.answer("Спочатку задай групу!", show_alert=True)

    target_date = datetime.now() if callback_data.target == "today" else datetime.now() + timedelta(days=1)
    schedule = await get_schedule(group["group_id"])

    if schedule:
        rich_msg = await format_day(schedule, target_date, group["group_id"], query.from_user.id)
    else:
        rich_msg = InputRichMessage(blocks=[InputRichBlockParagraph(text="❌ Помилка API")])

    with suppress(TelegramBadRequest):
        await query.message.edit_text(
            text="Твій розклад (Rich Messages не підтримуються клієнтом)",
            rich_message=rich_msg,
            reply_markup=get_main_menu(group["group_id"]),
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
    if callback_data.target == "today":
        track_live_view(query.message.chat.id, query.message.message_id, "today", group["group_id"], query.from_user.id)
    else:
        untrack_live_view(query.message.chat.id)
    await query.answer()


@router.callback_query(WeekCB.filter())
async def cb_week(query: CallbackQuery, callback_data: WeekCB):
    group = await get_group(query.from_user.id)
    if not group: return await query.answer("Спочатку задай групу!", show_alert=True)

    now = datetime.now()
    if callback_data.type in ("current", "next"):
        target_date = now if callback_data.type == "current" else now + timedelta(days=7)
    else:
        current_is_first = get_week_type(now) == "scheduleFirstWeek"
        target_date = now if (callback_data.type == "first") == current_is_first else now + timedelta(days=7)

    schedule = await get_schedule(group["group_id"])

    if schedule:
        rich_msg = await format_week(schedule, target_date, group["group_id"], query.from_user.id)
    else:
        rich_msg = InputRichMessage(blocks=[InputRichBlockParagraph(text="❌ Помилка API")])

    wt = "first" if get_week_type(target_date) == "scheduleFirstWeek" else "second"

    with suppress(TelegramBadRequest):
        await query.message.edit_text(
            text="Твій розклад (Rich Messages не підтримуються клієнтом)",
            rich_message=rich_msg,
            reply_markup=week_nav_keyboard(wt),
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
    is_current_week = (
            target_date.isocalendar()[1] == now.isocalendar()[1]
            and target_date.isocalendar()[0] == now.isocalendar()[0]
    )
    if is_current_week:
        track_live_view(query.message.chat.id, query.message.message_id, "week_current", group["group_id"],
                        query.from_user.id)
    else:
        untrack_live_view(query.message.chat.id)
    await query.answer()


@router.callback_query(FilterCB.filter())
async def cb_filter_subjects(query: CallbackQuery, callback_data: FilterCB):
    untrack_live_view(query.message.chat.id)
    group = await get_group(query.from_user.id)
    if not group: return await query.answer("Спочатку задай групу!", show_alert=True)

    subjects = await get_all_group_subjects(group["group_id"])
    if not subjects: return await query.answer("❌ Не знайдено предметів")

    page = callback_data.page
    PAGE_SIZE = 7

    if callback_data.action == "toggle":
        subj_name = subjects[callback_data.idx]
        is_now_hidden = await toggle_hidden_subject(query.from_user.id, group["group_id"], subj_name)
        status_msg = "❌ Приховано з розкладу" if is_now_hidden else "✅ Додано в розклад"
        await query.answer(status_msg)

    hidden = await get_hidden_subjects(query.from_user.id, group["group_id"])
    start = page * PAGE_SIZE
    chunk = subjects[start:start + PAGE_SIZE]

    builder = InlineKeyboardBuilder()
    for i, s in enumerate(chunk):
        real_idx = start + i
        mark = "❌" if s in hidden else "✅"
        btn_text = f"{mark} {s[:32]}..." if len(s) > 35 else f"{mark} {s}"
        builder.button(text=btn_text, callback_data=FilterCB(action="toggle", page=page, idx=real_idx))

    builder.adjust(1)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=FilterCB(action="list", page=page - 1).pack()))
    nav_buttons.append(
        InlineKeyboardButton(text=f"Стор. {page + 1}/{(len(subjects) - 1) // PAGE_SIZE + 1}", callback_data="noop"))
    if start + PAGE_SIZE < len(subjects):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=FilterCB(action="list", page=page + 1).pack()))

    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="🏠 Головне меню", callback_data=MenuCB(action="main").pack()))

    text = (
        "🎯 *Налаштування твоїх предметів*\n\n"
        "Натискай на назву, щоб приховати або повернути предмет у розклад:\n"
        "✅ — відображається у розкладі\n"
        "❌ — приховано (вибіркова, яку ти не відвідуєш)"
    )

    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())
    if callback_data.action != "toggle":
        await query.answer()


@router.callback_query(LinkSubjCB.filter(F.idx == -1))
async def cb_link_subjects_list(query: CallbackQuery, callback_data: LinkSubjCB):
    untrack_live_view(query.message.chat.id)
    group = await get_group(query.from_user.id)
    if not group: return await query.answer("Спочатку задай групу!", show_alert=True)

    subjects = await get_visible_subjects(query.from_user.id, group["group_id"])
    if not subjects:
        return await query.answer(
            "Усі предмети приховані. Зайди в «Мої предмети», щоб щось увімкнути.", show_alert=True
        )

    page = callback_data.page
    PAGE_SIZE = 7
    start = page * PAGE_SIZE
    chunk = subjects[start:start + PAGE_SIZE]

    builder = InlineKeyboardBuilder()
    for i, s in enumerate(chunk):
        real_idx = start + i
        builder.button(text=s[:35], callback_data=LinkSubjCB(page=page, idx=real_idx))
    builder.adjust(1)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=LinkSubjCB(page=page - 1, idx=-1).pack()))
    nav_buttons.append(InlineKeyboardButton(text=f"Стор. {page + 1}", callback_data="noop"))
    if start + PAGE_SIZE < len(subjects):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=LinkSubjCB(page=page + 1, idx=-1).pack()))

    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="🏠 Головне меню", callback_data=MenuCB(action="main").pack()))

    with suppress(TelegramBadRequest):
        await query.message.edit_text(
            "🔗 Обери предмет для налаштування посилання:\n"
            "_(показані лише ті, що активні в «Моїх предметах»)_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=builder.as_markup(),
        )
    await query.answer()


@router.callback_query(LinkSubjCB.filter(F.idx >= 0))
async def cb_link_subject_detail(query: CallbackQuery, callback_data: LinkSubjCB):
    group = await get_group(query.from_user.id)
    subjects = await get_visible_subjects(query.from_user.id, group["group_id"])  # ← тот же список, что и в списке выше
    subject = subjects[callback_data.idx]

    builder = InlineKeyboardBuilder()
    for p_type, icon in TYPE_ICONS.items():
        exists = await get_link(group["group_id"], subject, p_type)
        mark = "✅" if exists else "➕"
        builder.button(text=f"{icon} {p_type} {mark}",
                       callback_data=LinkTypeCB(idx=callback_data.idx, pair_type=p_type))

    builder.button(text="⬅️ Назад до списку", callback_data=LinkSubjCB(page=callback_data.page, idx=-1))
    builder.adjust(1)

    with suppress(TelegramBadRequest):
        await query.message.edit_text(f"📚 *{subject}*\nОбери тип заняття:", parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=builder.as_markup())
    await query.answer()



@router.callback_query(LinkTypeCB.filter())
async def cb_link_edit(query: CallbackQuery, callback_data: LinkTypeCB, state: FSMContext):
    group = await get_group(query.from_user.id)
    subjects = await get_visible_subjects(query.from_user.id, group["group_id"])  # ← и тут тоже
    subject = subjects[callback_data.idx]

    link = await get_link(group["group_id"], subject, callback_data.pair_type)

    await state.set_state(BotStates.wait_link)
    await state.update_data(subject=subject, pair_type=callback_data.pair_type, msg_id=query.message.message_id)

    text = (f"🔗 *{subject}* ({callback_data.pair_type})\n\nПоточне: `{link}`\n\nНадішли нове посилання або `-` щоб видалити."
            if link else
            f"🔗 *{subject}* ({callback_data.pair_type})\n\nПосилання не задано. Надішли його повідомленням.")

    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_menu())
    await query.answer()

@router.callback_query(F.data == "noop")
async def cb_noop(query: CallbackQuery):
    await query.answer()

@router.message(StateFilter(BotStates.wait_group, BotStates.wait_link))
async def handle_inputs(message: Message, state: FSMContext, bot: Bot):
    current_state = await state.get_state()
    data = await state.get_data()
    msg_id = data.get("msg_id")

    with suppress(TelegramBadRequest):
        await message.delete()

    if current_state == BotStates.wait_group:
        groups = await api_get_all_groups()
        norm_text = message.text.lower().replace("-", "").replace(" ", "")
        result = next((g for g in groups if g["groupName"].lower().replace("-", "") == norm_text),
                      None) if groups else None

        if result:
            await set_group(message.from_user.id, result["groupName"], result["id"])
            await state.clear()
            with suppress(TelegramBadRequest):
                await bot.edit_message_text(f"✅ Група *{result['groupName']}* збережена!", chat_id=message.chat.id,
                                            message_id=msg_id, parse_mode=ParseMode.MARKDOWN,
                                            reply_markup=get_main_menu(result["id"]))
        else:
            with suppress(TelegramBadRequest):
                await bot.edit_message_text(f"❌ Групу *{message.text}* не знайдено. Спробуй ще раз:",
                                            chat_id=message.chat.id, message_id=msg_id, parse_mode=ParseMode.MARKDOWN,
                                            reply_markup=get_cancel_menu())

    elif current_state == BotStates.wait_link:
        group = await get_group(message.from_user.id)
        subject, pair_type = data["subject"], data["pair_type"]

        await set_link(group["group_id"], subject, pair_type, message.text)
        await state.clear()

        builder = InlineKeyboardBuilder()
        builder.button(text="🏠 Головне меню", callback_data=MenuCB(action="main"))
        text = "❌ Посилання видалено!" if message.text == "-" else "✅ Посилання збережено!"

        with suppress(TelegramBadRequest):
            await bot.edit_message_text(text, chat_id=message.chat.id, message_id=msg_id,
                                        reply_markup=builder.as_markup())
