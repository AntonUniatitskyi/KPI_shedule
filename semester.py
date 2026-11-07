import logging
from datetime import date, datetime, timedelta

from config import SEMESTER_START

FIRST_WEEK = "scheduleFirstWeek"
SECOND_WEEK = "scheduleSecondWeek"

MIN_AGREEMENT = 0.85

_anchor: date = SEMESTER_START


def get_anchor() -> date:
    return _anchor


def week_type_for(d: date | datetime) -> str:
    if isinstance(d, datetime):
        d = d.date()
    weeks = (d - _anchor).days // 7
    return FIRST_WEEK if weeks % 2 == 0 else SECOND_WEEK


def _mondays(schedule: dict, week_key: str) -> set[date]:
    mondays: set[date] = set()
    for day in schedule.get(week_key) or []:
        for pair in day.get("pairs") or []:
            for raw in pair.get("dates") or []:
                try:
                    d = date.fromisoformat(raw)
                except (TypeError, ValueError):
                    continue
                mondays.add(d - timedelta(days=d.weekday()))
    return mondays


def _parity(monday: date, ref: date) -> int:
    return ((monday - ref).days // 7) % 2


def update_anchor_from_schedule(schedule: dict) -> None:
    global _anchor
    if not isinstance(schedule, dict):
        return

    first = _mondays(schedule, FIRST_WEEK)
    second = _mondays(schedule, SECOND_WEEK)
    if not first or not second:
        return  # у цій групі немає пар із датами — нічого не міняємо

    ref = min(first)
    total = len(first) + len(second)
    agree0 = (sum(1 for m in first if _parity(m, ref) == 0)
              + sum(1 for m in second if _parity(m, ref) == 1))
    agree1 = total - agree0

    if agree0 >= agree1:
        candidate, agree = ref, agree0
    else:
        candidate, agree = ref + timedelta(days=7), agree1

    ratio = agree / total
    if ratio < MIN_AGREEMENT:
        logging.warning("Якір тижня не оновлено: дані суперечливі (збіг %.0f%%)", ratio * 100)
        return

    if candidate == _anchor:
        return

    if _parity(candidate, _anchor) != 0:
        logging.warning("Парність тижнів змінилась: якір %s -> %s", _anchor, candidate)
    else:
        logging.info("Якір тижня оновлено: %s -> %s", _anchor, candidate)
    _anchor = candidate