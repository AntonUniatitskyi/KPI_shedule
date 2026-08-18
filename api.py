import logging
from datetime import datetime

import aiohttp

from config import CACHE_TTL

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

SCHEDULE_CACHE = {}

async def fetch_json(url: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=HEADERS, timeout=5) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logging.error(f"API Error: {e}")
    return None

async def api_get_all_groups():
    return await fetch_json("https://api.campus.kpi.ua/schedule/status")

async def get_schedule(group_id: int, force: bool = False):
    now_ts = datetime.now().timestamp()
    if not force and group_id in SCHEDULE_CACHE:
        data, ts = SCHEDULE_CACHE[group_id]
        if now_ts - ts < CACHE_TTL:
            return data

    data = await fetch_json(f"https://api.campus.kpi.ua/schedule/lessons?groupId={group_id}")
    if data:
        SCHEDULE_CACHE[group_id] = (data, now_ts)
    return data


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
    return sorted(list(subjects))