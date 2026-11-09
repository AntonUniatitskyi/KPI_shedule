import os
import time
from collections import Counter
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from api import api_status
from config import ADMIN_ID, DB_NAME, START_TS
from db import get_stats
from handlers.errors import ERROR_TIMES
from live_views import LIVE_VIEWS

router = Router()


def _rss_mb() -> float | None:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return None


def _uptime(sec: float) -> str:
    d, rem = divmod(int(sec), 86400)
    h, rem = divmod(rem, 3600)
    return f"{d}д {h}г {rem // 60}хв"


@router.message(Command("stats"), F.chat.type == "private")
async def cmd_stats(message: Message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        return

    s = await get_stats()
    api = api_status()
    kinds = Counter(v["kind"] for v in LIVE_VIEWS.values())
    errors_24h = sum(1 for t in ERROR_TIMES if time.time() - t < 86400)
    rss = _rss_mb()
    ram_text = f"{rss:.0f} МБ" if rss else "н/д"
    db_mb = os.path.getsize(DB_NAME) / 1024 / 1024
    top = "\n".join(f"  • {escape(name, quote=False)} — {cnt}" for name, cnt in s["top_groups"]) or "  —"

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👤 Користувачів із групою (ЛС): <b>{s['users']}</b>\n"
        f"🎓 Унікальних груп: <b>{s['groups']}</b>\n"
        f"💬 Привʼязаних чатів: <b>{s['chats']}</b>\n"
        f"🔗 Лінків: <b>{s['links']}</b> · приховують предмети: <b>{s['with_hidden']}</b>\n\n"
        f"🔴 Live-вʼю: <b>{len(LIVE_VIEWS)}</b> (сьогодні: {kinds['today']}, тиждень: {kinds['week_current']})\n"
        f"🌐 API: невдач поспіль <b>{api['fail_streak']}</b>, у кеші {api['cached']}\n"
        f"⚠️ Помилок за 24 год: <b>{errors_24h}</b>\n\n"
        f"⏱ Аптайм: {_uptime(time.time() - START_TS)}\n"
        f"🧠 RAM: {ram_text} · БД: {db_mb:.1f} МБ\n\n"
        f"<b>Топ груп</b>\n{top}"
    )
    await message.answer(text)