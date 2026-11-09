import zlib
import logging
from contextlib import suppress
from datetime import timedelta
from html import escape
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    EphemeralMessageParameters,
    InlineKeyboardButton,
    InputRichBlockParagraph,
    InlineKeyboardMarkup,
    InputRichMessage,
    LinkPreviewOptions,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api import api_get_all_groups, get_all_group_subjects, get_schedule
from callbacks import BotStates, DayCB, FilterCB, LinkSubjCB, LinkTypeCB, MenuCB, WeekCB
from config import TYPE_ICONS, now_kyiv
from db import (
    get_chats_for_group,
    get_hidden_subjects,
    get_link,
    is_group_chat,
    resolve_group,
    set_chat_group,
    set_group,
    set_link,
    toggle_hidden_subject,
)
from formatting import (
    format_day,
    format_week,
    get_subject_by_id,
    get_visible_subjects,
    get_week_type,
    get_what_now,
    normalize_group_name,
)
from keyboards import LAST_REFRESH, get_cancel_menu, get_main_menu, week_nav_keyboard
from live_views import track_live_view, untrack_live_view

router = Router()



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


async def send_menu(message: Message, bot: Bot, text: str, reply_markup: InlineKeyboardMarkup):
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


async def is_group_admin(bot: Bot, user_id: int, group_id: int) -> bool:
    for chat_id in await get_chats_for_group(group_id):
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except TelegramAPIError:
            continue  # бота прибрали з чату або чат недоступний
        if member.status in ("creator", "administrator"):
            return True
    return False


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



@router.message(Command("start", "menu"))
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if is_group_chat(message.chat):
        group = await resolve_group(message.from_user.id, message.chat)
        if not group:
            return await message.reply(
                "👋 Цей чат ще не привʼязаний до групи.\n"
                "Адмін має виконати: <code>/setgroup ІЦ-12</code>"
            )
        safe_name = escape(group["group_name"], quote=False)
        return await send_menu(
            message, bot,
            f"👋 <b>Бот розкладу КПІ</b> — {safe_name}\nОбери дію:",
            get_main_menu(group["group_id"], owner=message.from_user.id, in_group=True),
        )
    await message.reply("👋 <b>Бот розкладу КПІ</b>\n\nОбери дію:", reply_markup=get_main_menu())


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
    safe_name = escape(result["groupName"], quote=False)
    await message.reply(f"✅ Чат привʼязано до групи <b>{safe_name}</b>. Відкрий меню: /menu")



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
            reply_markup=get_main_menu(group["group_id"] if group else None, callback_data.owner, in_group),
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

    await get_schedule(group["group_id"], force=True)
    LAST_REFRESH[group["group_id"]] = now_kyiv()
    now_str = now_kyiv().strftime("%H:%M:%S")
    await query.answer("✅ Оновлено!")

    with suppress(TelegramBadRequest):
        await edit_screen(query, bot,
            f"🏠 <b>Головне меню</b>\n<i>🔄 Оновлено о {now_str}</i>",
            reply_markup=get_main_menu(group["group_id"], callback_data.owner, in_group),
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
            reply_markup=get_main_menu(group["group_id"], callback_data.owner, in_group),
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
            reply_markup=get_main_menu(group["group_id"], callback_data.owner, in_group),
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
                                            reply_markup=get_main_menu(result["id"]))
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

        if shared and not await is_group_admin(bot, message.from_user.id, group["group_id"]):
            await state.clear()
            with suppress(TelegramBadRequest):
                await bot.edit_message_text(
                    "⛔ Спільні лінки може задавати тільки адмін чату.",
                    chat_id=message.chat.id,
                    message_id=msg_id,
                    reply_markup=get_main_menu(group["group_id"]),
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