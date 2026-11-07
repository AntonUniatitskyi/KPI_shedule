import asyncio
import logging
import time

import aiohttp

from config import API_TIMEOUT, CACHE_TTL, GROUPS_TTL, STALE_MAX_AGE
from semester import update_anchor_from_schedule

API_BASE = "https://api.campus.kpi.ua"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

_session: aiohttp.ClientSession | None = None
_cache: dict[str, tuple[object, float]] = {}   # key -> (дані, monotonic-час збереження)
_locks: dict[str, asyncio.Lock] = {}


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
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        logging.error("API помилка для %s: %r", url, e)
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