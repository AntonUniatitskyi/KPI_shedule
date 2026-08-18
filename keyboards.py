from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from callbacks import DayCB, FilterCB, LinkSubjCB, MenuCB, WeekCB

LAST_REFRESH: dict[int, datetime] = {}

def get_main_menu(group_id: int | None = None):
    refresh_label = "🔄 Оновити"
    if group_id and group_id in LAST_REFRESH:
        mins_ago = int((datetime.now() - LAST_REFRESH[group_id]).total_seconds() // 60)
        refresh_label = "🔄 Оновити" if mins_ago > 30 else f"🔄 Оновлено {mins_ago} хв тому"
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 Що зараз?", callback_data=MenuCB(action="now"), style="primary")
    builder.button(text="📅 Сьогодні", callback_data=DayCB(target="today"), style="primary")
    builder.button(text="📅 Завтра", callback_data=DayCB(target="tomorrow"), style="primary")
    builder.button(text="🗓 Цей тиж.", callback_data=WeekCB(type="current"), style="primary")
    builder.button(text="🗓 Наступ.", callback_data=WeekCB(type="next"), style="primary")
    builder.button(text="⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯", callback_data="noop")
    builder.button(text="🎯 Мої предмети", callback_data=FilterCB(action="list", page=0))
    builder.button(text="🔗 Лінки", callback_data=LinkSubjCB(page=0))
    builder.button(text="📚 Задати групу", callback_data=MenuCB(action="set_group"))
    builder.button(text=refresh_label, callback_data=MenuCB(action="refresh"), style="success")
    builder.adjust(1, 2, 2, 1, 2, 2)
    return builder.as_markup()


def get_cancel_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Скасувати", callback_data=MenuCB(action="main").pack(), style="danger")
    return builder.as_markup()


def week_nav_keyboard(current_week_type: str):
    other = "second" if current_week_type == "first" else "first"
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️", callback_data=WeekCB(type=other))
    builder.button(text="🏠", callback_data=MenuCB(action="main"))
    builder.button(text="➡️", callback_data=WeekCB(type=other))
    builder.adjust(3)
    return builder.as_markup()
