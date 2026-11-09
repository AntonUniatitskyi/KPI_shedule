# KPI Schedule Bot

A Telegram bot that shows class schedules for KPI (Kyiv Polytechnic Institute) groups. Built on [aiogram 3](https://docs.aiogram.dev/) and Telegram's newest Bot API features: **Rich Messages** (real tables), **buttons inside message text**, and **ephemeral messages** (replies only the sender can see).

Data comes live from `api.campus.kpi.ua`. The bot works both in private chats and in group chats, where every member gets a personal answer based on their own subject selection.

## Features

- **Rich table view** — day and week schedules are rendered as real tables: time, subject, teacher, room and a 🔗 button for the meeting link.
- **"What's now?"** — shows the class in progress or the next one *you* actually have (hidden subjects are skipped), what comes after it, and a note when there is a gap.
- **Self-updating views (private chats)** — "Today" and "This week" repaint themselves at every bell and at midnight; the class in progress gets a 🟢 marker.
- **Personal subject filters** — hide electives you don't attend. The selection is stored per user and per schedule group, so it follows you between private chat and group chats.
- **Meeting links on two layers**
  - *Personal* links: only you see them.
  - *Shared* links: set by the admins of a connected group chat, shown to everyone in that chat unless a member has their own personal link for the same subject.
  - In a private chat only personal links are shown.
- **Group chats** — an admin binds the chat to a schedule group (`/setgroup`); every member opens their own menu with `/menu`. Replies are ephemeral, so the chat stays clean and each person sees their own schedule.
- **Automatic week parity** — the first/second week is derived from the dates in the API data itself (majority vote with a sanity threshold), with a configurable fallback.
- **Resilient API layer** — shared HTTP session with a timeout, per-key request de-duplication, 5-minute cache, and stale data served for up to 24 hours if the API is down. Manual refresh is rate-limited per group and honestly reports when data is stale.
- **Owner notifications** — unhandled errors (throttled, no user content) and start-up are reported to the owner in Telegram.

## Requirements

- Python 3.12 (what the Docker image uses and what the code is developed on)
- A bot token from [@BotFather](https://t.me/BotFather)
- **aiogram ≥ 3.31.0** — Rich Messages arrived in 3.30, buttons inside text and ephemeral messages in 3.31. Older versions fail on import.

## Project structure

```
.
├── main.py            # entry point: bot, command lists, polling, graceful shutdown
├── config.py          # token, admin id, TTLs, bell schedule, day names, timezone
├── semester.py        # week parity: anchor derived from API data
├── api.py             # aiohttp client, cache, stale fallback, refresh cooldown
├── db.py              # aiosqlite: groups, chat bindings, hidden subjects, links
├── access.py          # cached "is this user an admin of a connected chat" check
├── formatting.py      # builds Rich Message blocks (tables, headings, "what's now")
├── keyboards.py       # inline keyboards
├── callbacks.py       # FSM states and CallbackData classes
├── texts.py           # help / intro texts
├── live_views.py      # background task that repaints live messages
├── notifier.py        # throttled notifications to the bot owner
├── handlers/
│   ├── __init__.py    # assembles the root router (order matters)
│   ├── common.py      # shared helpers: edit_screen, send_menu, access checks
│   ├── commands.py    # /start /help /menu /setgroup
│   ├── chats.py       # bot added/removed, group → supergroup migration
│   ├── menu.py        # main menu, what's now, day, week, refresh
│   ├── subjects.py    # "My subjects" filter
│   ├── links.py       # personal and shared links (private chat only)
│   ├── inputs.py      # text input in private chat (group name, URL)
│   └── errors.py      # global error handler → log + owner notification
├── backup.sh          # consistent SQLite backup with rotation
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

Dependencies are one-way: `handlers/*` import everything else, nothing imports `handlers`. Inside the package, `common.py` imports no sibling modules, so there are no cycles.

## Configuration

Create a `.env` file in the project root:

```
TG_TOKEN=123456789:your-telegram-bot-token
ADMIN_ID=123456789
```

| Variable   | Required | Meaning |
|------------|----------|---------|
| `TG_TOKEN` | yes      | Bot token from BotFather |
| `ADMIN_ID` | no       | Telegram user id of the owner; receives error and start-up notifications. Unset or `0` disables them. |

Tunable constants live in `config.py`:

| Constant           | Default | Meaning |
|--------------------|---------|---------|
| `CACHE_TTL`        | 300 s   | How long a schedule counts as fresh |
| `GROUPS_TTL`       | 3600 s  | Cache for the list of groups |
| `STALE_MAX_AGE`    | 24 h    | How long old data may be served if the API is down |
| `API_TIMEOUT`      | 5 s     | HTTP timeout |
| `REFRESH_COOLDOWN` | 60 s    | Minimum gap between forced refreshes of one group |
| `SEMESTER_START`   | —       | Fallback Monday of a "first" week, used only until the first schedule is loaded |
| `KPI_BELLS`        | —       | Class start/end times |

## Running

### Docker (recommended)

```bash
docker compose up -d --build
docker compose logs -f
```

The SQLite database lives in `./data` (mounted into the container). The compose file limits logs to 3 × 10 MB and memory to 400 MB.

**Updating:** copy the new files, then rebuild without cache so new dependency versions and files are picked up:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Using the bot

### Private chat

| Command  | What it does |
|----------|--------------|
| `/start` | Intro and instructions with the main menu |
| `/menu`  | Main menu |
| `/help`  | The instructions again |

Start with **📚 Set group** (e.g. `ІЦ-12`), hide subjects you don't attend in **🎯 My subjects**, optionally add your own links in **🔗 Links**.

Admins of a connected group chat also see **👥 Shared links** to set links for the whole group.

### Group chat

1. Add the bot to the chat.
2. A chat admin runs `/setgroup ІЦ-12` once.
3. Anyone runs `/menu` — the reply is visible only to them and respects their hidden subjects and links.

| Command     | Who    | What it does |
|-------------|--------|--------------|
| `/menu`     | anyone | Open your own menu (ephemeral) |
| `/help`     | anyone | Short instructions (ephemeral) |
| `/setgroup` | admins | Bind the chat to a schedule group |

Buttons carry their owner's id, so pressing someone else's menu is refused. Personal and shared links are managed in the private chat with the bot.

If the bot doesn't receive commands in a group, disable *Group Privacy* for it in BotFather (`/setprivacy` → Disable).

## Data

SQLite file `data/bot_data.db` (WAL mode):

| Table                 | Contents |
|-----------------------|----------|
| `user_groups`         | Each user's chosen schedule group |
| `chat_groups`         | Group chat → schedule group binding (removed when the bot leaves; migrated when a group becomes a supergroup) |
| `user_hidden_subjects`| Per user and group: subjects hidden from views |
| `subject_links`       | Links per group, subject and class type. `owner_id = 0` means a shared link, otherwise the user's personal one |

The schema is created and migrated automatically on start-up.

### Backups

```bash
./backup.sh
```

Uses SQLite's backup API inside the container, so it is safe while the bot is running. Copies go to `data/backups/`, the 14 newest are kept. Daily via cron:

```
0 4 * * * /path/to/project/backup.sh >> /path/to/project/data/backups/backup.log 2>&1
```

Restore:

```bash
docker compose down
cp data/backups/bot_<stamp>.db data/bot_data.db
rm -f data/bot_data.db-wal data/bot_data.db-shm
docker compose up -d
```

## How it works

- **Week parity.** Every lesson in the API carries a list of concrete dates. `semester.py` checks which parity of week-number-since-anchor those dates fall on for the first-week and second-week lists, and accepts a new anchor only if at least 85 % of the dates agree. A change of parity (e.g. a new semester) is logged as a warning.
- **Cache and refresh.** `api.py` keeps one entry per key with a monotonic timestamp. Concurrent requests for the same key share one HTTP call. The refresh button reports one of four outcomes: fresh, too soon (with seconds to wait), stale (API down, cache served), or no data.
- **Ephemeral menus.** In groups, `/menu` is registered as an ephemeral command and answered with ephemeral message parameters. Button presses on such a message are edited with the ephemeral edit method; `edit_screen()` in `handlers/common.py` picks the right method. If Telegram rejects an ephemeral reply, the bot falls back to a normal message.
- **Live views.** In private chats the message is registered in `live_views.LIVE_VIEWS`; a background task wakes at each bell start/end and at midnight. Navigating away untracks it. Live views are disabled in groups.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `ImportError` for Rich Message types / `RichTextButton` | aiogram is older than 3.31 |
| `TypeError: … got an unexpected keyword argument` after an update | Not all files were copied, or the image was not rebuilt (`build --no-cache`) |
| `NameError`/old behaviour right after a deploy | The container still runs an old image; rebuild |
| Screen doesn't update and nothing is logged | Some edits are wrapped in `suppress(TelegramBadRequest)`; temporarily log the exception to see what Telegram rejected |
| Commands ignored in a group | Group Privacy is on; disable it in BotFather |
| "Shared links" button missing | You're not an admin of any chat bound to your group, or the chat isn't bound yet (`/setgroup`) |

## Notes

- Unofficial project; schedule data belongs to its source, `api.campus.kpi.ua`.
- The Bot API features used here are new. If Telegram renames fields or changes behaviour, check aiogram's changelog and the classes imported in `formatting.py`, `keyboards.py` and `handlers/common.py` first.
- No Telegram Premium features are required.