from contextlib import suppress
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputRichBlockParagraph, InputRichMessage, LinkPreviewOptions

from api import get_schedule, refresh_schedule, schedule_age_seconds
from callbacks import BotStates, DayCB, MenuCB, WeekCB
from config import now_kyiv
from db import is_group_chat, resolve_group
from formatting import format_day, format_week, get_week_type, get_what_now
from handlers.common import deny_foreign, dm_only, edit_screen, menu_markup, no_group_text
from keyboards import get_cancel_menu, week_nav_keyboard
from live_views import track_live_view, untrack_live_view

router = Router()


@router.callback_query(MenuCB.filter(F.action == "main"))
async def cb_main_menu(query: CallbackQuery, callback_data: MenuCB, state: FSMContext, bot: Bot):
    if await deny_foreign(query, callback_data):
        return
    untrack_live_view(query.message.chat.id)
    await state.clear()
    in_group = is_group_chat(query.message.chat)
    group = await resolve_group(query.from_user.id, query.message.chat)
    with suppress(TelegramBadRequest):
        await edit_screen(query, bot,
            "🏠 <b>Головне меню</b>",
            reply_markup=await menu_markup(bot, query.from_user.id, group["group_id"] if group else None,
                                           callback_data.owner, in_group),
        )
    await query.answer()


@router.callback_query(MenuCB.filter(F.action == "set_group"))
async def cb_set_group(query: CallbackQuery, state: FSMContext, bot: Bot):
    if await dm_only(query):
        return
    untrack_live_view(query.message.chat.id)
    await state.set_state(BotStates.wait_group)
    await state.update_data(msg_id=query.message.message_id)
    with suppress(TelegramBadRequest):
        await edit_screen(query, bot, "Введи точну назву групи (наприклад, ІЦ-12):", reply_markup=get_cancel_menu())
    await query.answer()


@router.callback_query(MenuCB.filter(F.action == "refresh"))
async def cb_refresh(query: CallbackQuery, callback_data: MenuCB, bot: Bot):
    if await deny_foreign(query, callback_data):
        return
    in_group = is_group_chat(query.message.chat)
    group = await resolve_group(query.from_user.id, query.message.chat)
    if not group:
        return await query.answer(no_group_text(in_group), show_alert=True)

    status, wait = await refresh_schedule(group["group_id"])

    if status == "cooldown":
        return await query.answer(f"⏳ Розклад щойно оновлювався. Спробуй через {wait} с.")
    if status == "none":
        return await query.answer("❌ API недоступний, і збережених даних немає.", show_alert=True)

    now_str = now_kyiv().strftime("%H:%M:%S")
    if status == "fresh":
        await query.answer("✅ Оновлено!")
        note = f"<i>🔄 Оновлено о {now_str}</i>"
    else:  # stale
        age = schedule_age_seconds(group["group_id"])
        age_txt = f"{int(age // 60)} хв тому" if age is not None else "раніше"
        await query.answer("⚠️ API недоступний, показую збережені дані.", show_alert=True)
        note = f"<i>⚠️ API недоступний. Дані з кешу (завантажено {age_txt})</i>"

    with suppress(TelegramBadRequest):
        await edit_screen(
            query, bot,
            f"🏠 <b>Головне меню</b>\n{note}",
            reply_markup=await menu_markup(bot, query.from_user.id, group["group_id"],
                                           callback_data.owner, in_group),
        )


@router.callback_query(MenuCB.filter(F.action == "now"))
async def cb_what_now(query: CallbackQuery, callback_data: MenuCB, bot: Bot):
    if await deny_foreign(query, callback_data):
        return
    untrack_live_view(query.message.chat.id)
    in_group = is_group_chat(query.message.chat)
    group = await resolve_group(query.from_user.id, query.message.chat)
    if not group:
        return await query.answer(no_group_text(in_group), show_alert=True)

    schedule = await get_schedule(group["group_id"])

    if schedule:
        rich_msg = await get_what_now(schedule, now_kyiv(), group["group_id"], query.from_user.id,
                                     include_shared=in_group)
    else:
        rich_msg = InputRichMessage(blocks=[InputRichBlockParagraph(text="❌ Помилка API")])

    with suppress(TelegramBadRequest):
        await edit_screen(query, bot,
            text="Твій розклад (Rich Messages не підтримуються клієнтом)",
            rich_message=rich_msg,
            reply_markup=await menu_markup(bot, query.from_user.id, group["group_id"],
                                           callback_data.owner, in_group),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    await query.answer()


@router.callback_query(DayCB.filter())
async def cb_day(query: CallbackQuery, callback_data: DayCB, bot: Bot):
    if await deny_foreign(query, callback_data):
        return
    in_group = is_group_chat(query.message.chat)
    group = await resolve_group(query.from_user.id, query.message.chat)
    if not group:
        return await query.answer(no_group_text(in_group), show_alert=True)

    target_date = now_kyiv() if callback_data.target == "today" else now_kyiv() + timedelta(days=1)
    schedule = await get_schedule(group["group_id"])

    if schedule:
        rich_msg = await format_day(schedule, target_date, group["group_id"], query.from_user.id,
                                    include_shared=in_group)
    else:
        rich_msg = InputRichMessage(blocks=[InputRichBlockParagraph(text="❌ Помилка API")])

    with suppress(TelegramBadRequest):
        await edit_screen(query, bot,
            text="Твій розклад (Rich Messages не підтримуються клієнтом)",
            rich_message=rich_msg,
            reply_markup=await menu_markup(bot, query.from_user.id, group["group_id"],
                                           callback_data.owner, in_group),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    if callback_data.target == "today" and not in_group:
        track_live_view(query.message.chat.id, query.message.message_id, "today", group["group_id"],
                        query.from_user.id)
    else:
        untrack_live_view(query.message.chat.id)
    await query.answer()


@router.callback_query(WeekCB.filter())
async def cb_week(query: CallbackQuery, callback_data: WeekCB, bot: Bot):
    if await deny_foreign(query, callback_data):
        return
    in_group = is_group_chat(query.message.chat)
    group = await resolve_group(query.from_user.id, query.message.chat)
    if not group:
        return await query.answer(no_group_text(in_group), show_alert=True)

    now = now_kyiv()
    if callback_data.type in ("current", "next"):
        target_date = now if callback_data.type == "current" else now + timedelta(days=7)
    else:
        current_is_first = get_week_type(now) == "scheduleFirstWeek"
        target_date = now if (callback_data.type == "first") == current_is_first else now + timedelta(days=7)

    schedule = await get_schedule(group["group_id"])

    if schedule:
        rich_msg = await format_week(schedule, target_date, group["group_id"], query.from_user.id,
                                     include_shared=in_group)
    else:
        rich_msg = InputRichMessage(blocks=[InputRichBlockParagraph(text="❌ Помилка API")])

    wt = "first" if get_week_type(target_date) == "scheduleFirstWeek" else "second"

    with suppress(TelegramBadRequest):
        await edit_screen(query, bot,
            text="Твій розклад (Rich Messages не підтримуються клієнтом)",
            rich_message=rich_msg,
            reply_markup=week_nav_keyboard(wt, callback_data.owner),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    is_current_week = (
            target_date.isocalendar()[1] == now.isocalendar()[1]
            and target_date.isocalendar()[0] == now.isocalendar()[0]
    )
    if is_current_week and not in_group:
        track_live_view(query.message.chat.id, query.message.message_id, "week_current", group["group_id"],
                        query.from_user.id)
    else:
        untrack_live_view(query.message.chat.id)
    await query.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(query: CallbackQuery):
    await query.answer()