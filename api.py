import asyncio
import logging
import time

import aiohttp

from config import API_TIMEOUT, CACHE_TTL, GROUPS_TTL, REFRESH_COOLDOWN, STALE_MAX_AGE
from semester import update_anchor_from_schedule

API_BASE = "https://api.campus.kpi.ua"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

_session: aiohttp.ClientSession | None = None
_cache: dict[str, tuple[object, float]] = {}   # key -> (дані, monotonic-час збереження)
_locks: dict[str, asyncio.Lock] = {}
_last_refresh_try: dict[int, float] = {}       # group_id -> час останньої спроби примусового оновлення
API_DOWN_THRESHOLD = 5
_fail_streak = 0
_alert_handler = None
_alert_tasks: set[asyncio.Task] = set()

def set_alert_handler(handler):
    global _alert_handler
    _alert_handler = handler



def _alert(text: str):
    if _alert_handler is None:
        return
    task = asyncio.create_task(_alert_handler(text))
    _alert_tasks.add(task)
    task.add_done_callback(_alert_tasks.discard)


def _note_result(ok: bool):
    global _fail_streak
    if ok:
        if _fail_streak >= API_DOWN_THRESHOLD:
            _alert("✅ API розкладу знову працює")
        _fail_streak = 0
    else:
        _fail_streak += 1
        if _fail_streak == API_DOWN_THRESHOLD:
            _alert(f"🔴 API розкладу недоступне ({API_DOWN_THRESHOLD} невдалих запитів поспіль). "
                   "Бот віддає дані з кешу.")


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
        )
    return _session


async def close_session():
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def fetch_json(url: str):
    try:
        async with _get_session().get(url) as resp:
            if resp.status != 200:
                logging.warning("API %s повернув HTTP %s", url, resp.status)
                _note_result(False)
                return None
            data = await resp.json(content_type=None)
            _note_result(True)
            return data
    except Exception as e:
        logging.error("API помилка для %s: %r", url, e)
        _note_result(False)
        return None


async def _cached_get(key: str, url: str, ttl: float, force: bool = False, on_fresh=None):
    requested = time.monotonic()

    if not force:
        entry = _cache.get(key)
        if entry and requested - entry[1] < ttl:
            return entry[0]

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        # Поки чекали на lock, хтось інший міг уже оновити кеш — тоді повторний запит не потрібен.
        entry = _cache.get(key)
        if entry and entry[1] >= requested:
            return entry[0]

        data = await fetch_json(url)
        if data:
            _cache[key] = (data, time.monotonic())
            if on_fresh is not None:
                try:
                    on_fresh(data)
                except Exception:
                    logging.exception("on_fresh для %s впав", key)
            return data

        entry = _cache.get(key)
        if entry and time.monotonic() - entry[1] < STALE_MAX_AGE:
            logging.warning("API недоступний, віддаю застарілі дані для %s", key)
            return entry[0]
        return None


async def api_get_all_groups():
    return await _cached_get("groups", f"{API_BASE}/schedule/status", GROUPS_TTL)


async def get_schedule(group_id: int, force: bool = False):
    return await _cached_get(
        f"schedule:{group_id}",
        f"{API_BASE}/schedule/lessons?groupId={group_id}",
        CACHE_TTL,
        force=force,
        on_fresh=update_anchor_from_schedule,
    )


def schedule_age_seconds(group_id: int) -> float | None:
    entry = _cache.get(f"schedule:{group_id}")
    return time.monotonic() - entry[1] if entry else None


async def refresh_schedule(group_id: int) -> tuple[str, int]:
    """Примусове оновлення з обмеженням частоти (на групу, а не на користувача).

    Повертає (статус, число):
      "fresh"    — розклад щойно завантажено з API;
      "cooldown" — зарано, число = скільки секунд зачекати;
      "stale"    — API недоступний, лишились старі дані з кешу;
      "none"     — API недоступний і даних немає.
    """
    now = time.monotonic()
    last = _last_refresh_try.get(group_id)
    if last is not None and now - last < REFRESH_COOLDOWN:
        return "cooldown", int(REFRESH_COOLDOWN - (now - last)) + 1
    _last_refresh_try[group_id] = now  # рахуємо і невдалі спроби, щоб не довбити лежачий API

    before = _cache.get(f"schedule:{group_id}")
    data = await get_schedule(group_id, force=True)
    after = _cache.get(f"schedule:{group_id}")

    if after is not None and (before is None or after[1] > before[1]):
        return "fresh", 0
    return ("stale", 0) if data else ("none", 0)


async def get_all_group_subjects(group_id: int) -> list[str]:
    schedule = await get_schedule(group_id)
    if not schedule:
        return []
    subjects = set()
    for wk in ("scheduleFirstWeek", "scheduleSecondWeek"):
        for d in schedule.get(wk, []):
            for p in d.get("pairs", []):
                if p.get("name"):
                    subjects.add(p["name"])
    return sorted(subjects)


def api_status() -> dict:
    return {"fail_streak": _fail_streak, "cached": len(_cache)}