# KPI Schedule Bot

A Telegram bot that shows the class schedule for KPI (Kyiv Polytechnic Institute) groups, built on [aiogram 3](https://docs.aiogram.dev/) and Telegram's **Rich Messages** (Bot API 10.1+).

Pulls live data from `api.campus.kpi.ua`, renders it as interactive tables inside Telegram, and keeps "today" / "this week" views updating themselves in the background — no need to re-open the chat to see when a class starts.

## Features

- **Rich table view** — day/week schedules render as real tables (time, subject, teacher, room, meeting link) instead of plain text.
- **Self-updating views** — the "Сьогодні" and "Цей тиждень" messages repaint themselves automatically at every class boundary (bell start/end) and at midnight, with a 🟢 marker on the class currently in progress.
- **Auto-expanding "today"** — in the weekly view, today's day block opens automatically; the rest stay collapsed.
- **Per-user subject filters** — hide electives/subjects you don't attend; hidden subjects disappear from every view, including the link manager.
- **Per-subject meeting links** — attach a Zoom/Meet/whatever link to any subject + class type (lecture/practice/lab); shown as a clickable cell in the table.
- **Resilient API layer** — schedule requests are cached (5 min TTL) and fall back to the last known good response if `api.campus.kpi.ua` is temporarily down, instead of showing an error.
- **Clean inline menu** — grouped, colour-coded buttons (`style="primary"/"success"/"danger"`), no Telegram Premium required.

## Requirements

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- **aiogram ≥ 3.30.0** — this is not optional. Rich Messages (`InputRichMessage`, button `style=`) are a very recent addition to the Bot API; older aiogram versions don't have these types at all and the bot will fail on import.

## Project structure

```
kpi_bot/
├── config.py       # constants: token, bell schedule, day names, cache TTL
├── db.py           # aiosqlite: saved groups, hidden subjects, subject links
├── api.py          # aiohttp client for api.campus.kpi.ua + in-memory schedule cache
├── callbacks.py     # FSM states + all CallbackData classes
├── formatting.py    # builds InputRichMessage blocks (tables, headings, details)
├── keyboards.py     # inline keyboards (main menu, cancel, week navigation)
├── live_views.py    # background task that repaints "live" messages
├── handlers.py       # the Router — all message/callback handlers
├── main.py           # entry point
├── requirements.txt
└── .gitignore
```

Dependency direction is one-way (`handlers` depends on everything else, nothing depends on `handlers`), so there are no circular imports.

## Setup

1. Clone the repo and enter the project folder.

   ```bash
   git clone <your-repo-url>
   cd kpi_bot
   ```

2. Create a virtual environment and install dependencies.

   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root with your bot token:

   ```
   TG_TOKEN=123456789:your-telegram-bot-token
   ```

4. Run the bot:

   ```bash
   python main.py
   ```

On first run, `bot_data.db` (SQLite) is created automatically — it stores each user's selected group, hidden subjects, and subject links. It's git-ignored by default; don't commit it.

## How it works, briefly

- `/start` shows the main menu. The user first picks their group ("Задати групу"), which is matched against the live group list from `api.campus.kpi.ua`.
- **Сьогодні / Цей тиждень** are "live" views: opening them registers the message in `live_views.LIVE_VIEWS`, and a background task (`live_view_updater`) wakes up at every bell start/end/midnight and re-renders any tracked message with fresh data — including moving the 🟢 "in progress" marker and re-opening the current day in the weekly view. Navigating away from these views (main menu, filters, link manager, etc.) untracks the message so it stops being auto-edited.
- **Мої предмети** lets a user hide subjects (electives, etc.) from all views. **Керувати лінками** only shows subjects that are *not* hidden, keeping both flows in sync.

## Notes

- This bot doesn't use Telegram Premium features (custom emoji on buttons require the *bot owner* to have Premium or a Fragment-purchased username). Button colouring via `style=` works for everyone.
- The Rich Messages API is new; if Telegram changes field names or behaviour, check `aiogram`'s changelog and the classes imported in `formatting.py` / `keyboards.py` first.