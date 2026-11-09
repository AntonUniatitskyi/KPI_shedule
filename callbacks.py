from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup


class BotStates(StatesGroup):
    wait_group = State()
    wait_link = State()


class MenuCB(CallbackData, prefix="menu"):
    action: str
    owner: int = 0


class DayCB(CallbackData, prefix="day"):
    target: str
    owner: int = 0


class WeekCB(CallbackData, prefix="week"):
    type: str
    owner: int = 0


class LinkSubjCB(CallbackData, prefix="lsub"):
    page: int
    idx: int = -1
    owner: int = 0
    shared: int = 0  # 1 — спільні лінки групи (тільки адмін)


class LinkTypeCB(CallbackData, prefix="ltp"):
    idx: int
    pair_type: str
    owner: int = 0
    shared: int = 0


class FilterCB(CallbackData, prefix="fltr"):
    action: str
    page: int
    idx: int = 0
    owner: int = 0