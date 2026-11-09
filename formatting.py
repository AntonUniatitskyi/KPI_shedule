import zlib
from datetime import datetime, timedelta

from aiogram.types import (
    InputRichBlockDetails,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichMessageButton,
    RichTextBold,
    RichTextButton,
    RichTextUrl,
)

from api import get_all_group_subjects
from config import DAY_NAMES, DAYS_MAP, KPI_BELLS, TYPE_ICONS, now_kyiv
from db import get_hidden_subjects, get_link
from semester import week_type_for


def get_table_headers() -> list[RichBlockTableCell]:
    headers = ["Час", "Предмет", "Викл.", "Ауд.", "Лінк"]
    return [
        RichBlockTableCell(text=RichTextBold(text=h), is_header=True, align="center", valign="middle")
        for h in headers
    ]

def short_name(full_name: str) -> str:
    parts = full_name.split()
    return f"{parts[0]} {parts[1][0]}." if len(parts) >= 2 else full_name


def is_pair_relevant(pair: dict, target_date: datetime) -> bool:
    dates = pair.get("dates", [])
    return True if not dates else target_date.strftime("%Y-%m-%d") in dates


def get_week_type(date: datetime) -> str:
    return week_type_for(date.date())

def get_active_pair_time(now: datetime) -> str | None:
    t = now.time()
    for start, end, _ in KPI_BELLS:
        if start <= t <= end:
            return start.strftime("%H:%M")
    return None

async def get_visible_subjects(user_id: int, group_id: int) -> list[str]:
    all_subjects = await get_all_group_subjects(group_id)
    hidden = await get_hidden_subjects(user_id, group_id)
    return [s for s in all_subjects if s not in hidden]


async def create_pair_row(pair: dict, group_id: int, user_id: int, is_active: bool = False,
                          include_shared: bool = False) -> list[RichBlockTableCell]:
    lecturer = pair.get("lecturer")
    teacher_name = lecturer.get("name", "Викладач не вказаний") if lecturer else "Викладач не вказаний"
    teacher = short_name(teacher_name) if teacher_name != "Викладач не вказаний" else teacher_name

    subject = pair.get("name", "Невідомий предмет")
    pair_type = pair.get("type", "")
    icon = TYPE_ICONS.get(pair_type, "📘")
    link = await get_link(user_id, group_id, subject, pair_type, include_shared)

    time_text = f"🟢 {pair['time'][:5]}" if is_active else pair["time"][:5]

    time_cell = RichBlockTableCell(text=time_text, align="center", valign="middle")

    subject_cell = RichBlockTableCell(
        text=[f"{icon} ", RichTextBold(text=subject), f" ({pair_type})"],
        align="left",
        valign="middle",
    )

    teacher_cell = RichBlockTableCell(text=teacher, align="left", valign="middle")

    location = pair.get("location")
    if location and location.get("title"):
        loc_uri = location.get("uri")
        loc_text = RichTextUrl(text=location["title"], url=loc_uri) if loc_uri else location["title"]
        location_cell = RichBlockTableCell(text=loc_text, align="center", valign="middle")
    else:
        location_cell = RichBlockTableCell(text="—", align="center", valign="middle")

    # коротка кнопка в окремій вузькій колонці: не розтягує таблицю
    if link:
        link_cell = RichBlockTableCell(
            text=RichTextButton(button=RichMessageButton(text="🔗", url=link, style="link")),
            align="center",
            valign="middle",
        )
    else:
        link_cell = RichBlockTableCell(text="—", align="center", valign="middle")

    return [time_cell, subject_cell, teacher_cell, location_cell, link_cell]


async def format_day(schedule: dict, date: datetime, group_id: int, user_id: int,
                     include_shared: bool = False) -> InputRichMessage:
    week_key = get_week_type(date)
    day_key = DAYS_MAP.get(date.weekday())
    blocks = []

    if not day_key:
        blocks.extend([
            InputRichBlockSectionHeading(text="Неділя — вихідний! 🎉", size=1),
            InputRichBlockParagraph(text="Відпочивай 🍻")
        ])
        return InputRichMessage(blocks=blocks)

    day = next((d for d in schedule.get(week_key, []) if d["day"] == day_key), None)
    blocks.append(InputRichBlockSectionHeading(text=f"📅 {DAY_NAMES[day_key]}", size=1))

    if not day or not day["pairs"]:
        blocks.append(InputRichBlockParagraph(text="🎉 Пар немає"))
        return InputRichMessage(blocks=blocks)

    hidden = await get_hidden_subjects(user_id, group_id)
    valid_pairs = [p for p in day["pairs"] if is_pair_relevant(p, date) and p.get("name") not in hidden]

    if not valid_pairs:
        blocks.append(InputRichBlockParagraph(text="🎉 Пар немає (решта приховані в налаштуваннях)"))
        return InputRichMessage(blocks=blocks)

    active_time = get_active_pair_time(now_kyiv()) if date.date() == now_kyiv().date() else None
    rows = [
        await create_pair_row(pair, group_id, user_id, is_active=(pair["time"][:5] == active_time),
                              include_shared=include_shared)
        for pair in valid_pairs
    ]

    table_cells = [get_table_headers()] + rows
    blocks.append(InputRichBlockTable(cells=table_cells, is_striped=True, is_bordered=True))

    return InputRichMessage(blocks=blocks)


async def format_week(schedule: dict, start_date: datetime, group_id: int, user_id: int,
                      include_shared: bool = False) -> InputRichMessage:
    week_key = get_week_type(start_date)
    week_name = "Перший тиждень" if week_key == "scheduleFirstWeek" else "Другий тиждень"
    days = schedule.get(week_key, [])

    hidden = await get_hidden_subjects(user_id, group_id)
    blocks = [InputRichBlockSectionHeading(text=f"📆 {week_name}", size=1)]

    monday = start_date - timedelta(days=start_date.weekday())
    has_pairs = False

    for day_idx in range(6):
        day_key = DAYS_MAP[day_idx]
        day_data = next((d for d in days if d["day"] == day_key), None)
        if not day_data or not day_data["pairs"]: continue

        current_day_date = monday + timedelta(days=day_idx)
        valid_pairs = [p for p in day_data["pairs"] if
                       is_pair_relevant(p, current_day_date) and p.get("name") not in hidden]
        if not valid_pairs: continue

        has_pairs = True
        is_today = current_day_date.date() == now_kyiv().date()
        active_time = get_active_pair_time(now_kyiv()) if is_today else None

        rows = [
            await create_pair_row(pair, group_id, user_id, is_active=(pair["time"][:5] == active_time),
                              include_shared=include_shared)
            for pair in valid_pairs
        ]

        table_cells = [get_table_headers()] + rows
        day_table = InputRichBlockTable(cells=table_cells, is_striped=True, is_bordered=True)

        blocks.append(
            InputRichBlockDetails(
                summary=f"📅 {DAY_NAMES[day_key]}" + (" 🟢" if is_today else ""),
                blocks=[day_table],
                is_open=is_today,
            )
        )

    if not has_pairs:
        blocks.append(InputRichBlockParagraph(text="🎉 Пар немає"))

    return InputRichMessage(blocks=blocks)


def _bell_name(start) -> str:
    return next((n for s, _, n in KPI_BELLS if s == start), "Пара")


def _pair_span(pair: dict):
    raw = (pair.get("time") or "")[:5]
    try:
        start = datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return None
    for s, e, _ in KPI_BELLS:
        if s == start:
            return s, e
    return start, (datetime(2000, 1, 1, start.hour, start.minute) + timedelta(minutes=90)).time()


async def get_what_now(schedule: dict, now: datetime, group_id: int, user_id: int,
                       include_shared: bool = False) -> InputRichMessage:
    blocks = []
    if now.weekday() == 6:
        blocks.extend([InputRichBlockSectionHeading(text="🔥 Що зараз?", size=2),
                       InputRichBlockParagraph(text="Сьогодні неділя, пар немає! Відпочивай 🍻")])
        return InputRichMessage(blocks=blocks)

    day_key = DAYS_MAP[now.weekday()]
    week_key = get_week_type(now)
    today_schedule = next((d for d in schedule.get(week_key, []) if d.get("day") == day_key), None)

    if not today_schedule or not today_schedule.get("pairs"):
        return InputRichMessage(blocks=[InputRichBlockParagraph(text="На сьогодні пар у розкладі немає. 🎉")])

    hidden = await get_hidden_subjects(user_id, group_id)
    available_pairs = [
        p for p in today_schedule.get("pairs", [])
        if p.get("name") not in hidden and is_pair_relevant(p, now)
    ]

    if not available_pairs:
        return InputRichMessage(blocks=[InputRichBlockParagraph(text="На сьогодні твоїх пар немає. 🎉")])

    spans = []
    for p in available_pairs:
        span = _pair_span(p)
        if span:
            spans.append((span[0], span[1], _bell_name(span[0]), p))
    spans.sort(key=lambda x: x[0])

    if not spans:
        return InputRichMessage(blocks=[InputRichBlockParagraph(text="Не вдалося визначити час пар на сьогодні.")])

    now_time = now.time()
    current_start = next((s for s, e, _, _ in spans if s <= now_time <= e), None)

    if current_start is not None:
        status, focus_start = "🟢 Зараз йде", current_start
    else:
        status = "🟡 Наступна"
        focus_start = next((s for s, _, _, _ in spans if s > now_time), None)

    if focus_start is None:
        return InputRichMessage(blocks=[InputRichBlockParagraph(text="Всі твої пари на сьогодні вже закінчились! 🌙")])

    group_pairs = [x for x in spans if x[0] == focus_start]
    end = max(x[1] for x in group_pairs)

    blocks.append(InputRichBlockSectionHeading(text=f"{status} {group_pairs[0][2]}", size=2))
    blocks.append(InputRichBlockParagraph(text=f"🕒 {focus_start.strftime('%H:%M')} - {end.strftime('%H:%M')}"))

    if current_start is None:
        next_bell = next((s for s, _, _ in KPI_BELLS if s > now_time), None)
        if next_bell is not None and focus_start > next_bell:
            blocks.append(InputRichBlockParagraph(
                text=f"☕ Найближчі пари за твоїм вибором — вікно, наступна о {focus_start.strftime('%H:%M')}"
            ))

    custom_headers = ["Предмет", "Викладач", "Ауд.", "Лінк"]
    header_cells = [
        RichBlockTableCell(text=RichTextBold(text=h), is_header=True, align="center", valign="middle")
        for h in custom_headers
    ]
    table_cells = [header_cells]
    for _, _, _, pair in group_pairs:
        row_data = await create_pair_row(pair, group_id, user_id, include_shared=include_shared)
        table_cells.append(row_data[1:])
    blocks.append(InputRichBlockTable(cells=table_cells, is_striped=True, is_bordered=True))

    if current_start is not None:
        nxt = next((x for x in spans if x[0] > now_time), None)
        if nxt:
            s, _, _, pair = nxt
            blocks.append(InputRichBlockParagraph(
                text=f"⏭ Далі: {s.strftime('%H:%M')} — {pair.get('name', 'Невідомий предмет')} ({pair.get('type', '')})"
            ))

    return InputRichMessage(blocks=blocks)


LATIN_TO_CYRILLIC = str.maketrans(
    "aceiopxykmtbh",
    "асеіорхукмтвн"
)

def normalize_group_name(s: str) -> str:
    if not s:
        return ""

    gr_name = s.lower().replace("-", "").replace(" ", "").translate(LATIN_TO_CYRILLIC)
    return gr_name

def get_subject_by_id(subjects: list[str], subj_id: int) -> str | None:
    for s in subjects:
        if zlib.crc32(s.encode()) == subj_id:
            return s
    return None