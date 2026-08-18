from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup

class BotStates(StatesGroup):
    wait_group = State()
    wait_link = State()


class MenuCB(CallbackData, prefix="menu"):
    action: str


class DayCB(CallbackData, prefix="day"):
    target: str


class WeekCB(CallbackData, prefix="week"):
    type: str


class LinkSubjCB(CallbackData, prefix="lsub"):
    page: int
    idx: int = -1


class LinkTypeCB(CallbackData, prefix="ltp"):
    idx: int
    pair_type: str


class FilterCB(CallbackData, prefix="fltr"):
    action: str
    page: int
    idx: int = 0
