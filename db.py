import aiosqlite

from config import DB_NAME


async def _migrate_links(db):
    async with db.execute("PRAGMA table_info(subject_links)") as cur:
        cols = {r[1] for r in await cur.fetchall()}

    if cols and "owner_id" not in cols:
        await db.execute("ALTER TABLE subject_links RENAME TO subject_links_old")
        cols = set()

    if not cols:
        await db.execute('''
                         CREATE TABLE subject_links
                         (
                             group_id     INTEGER,
                             subject_name TEXT,
                             pair_type    TEXT,
                             owner_id     INTEGER, -- 0 = общая ссылка группы
                             url          TEXT,
                             set_by       INTEGER,
                             PRIMARY KEY (group_id, subject_name, pair_type, owner_id)
                         )
                         ''')
        async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='subject_links_old'"
        ) as cur:
            has_old = await cur.fetchone()
        if has_old:
            # старые ссылки становятся общими; в ЛС они не показываются
            await db.execute('''
                             INSERT INTO subject_links (group_id, subject_name, pair_type, owner_id, url, set_by)
                             SELECT group_id, subject_name, pair_type, 0, url, NULL
                             FROM subject_links_old
                             ''')
            await db.execute("DROP TABLE subject_links_old")


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute('''
                         CREATE TABLE IF NOT EXISTS user_groups
                         (
                             user_key TEXT PRIMARY KEY,
                             group_name TEXT,
                             group_id INTEGER
                         )
                         ''')
        await db.execute('''
                         CREATE TABLE IF NOT EXISTS chat_groups
                         (
                             chat_id INTEGER PRIMARY KEY,
                             group_name TEXT,
                             group_id INTEGER,
                             set_by INTEGER
                         )
                         ''')
        await _migrate_links(db)
        await db.execute('''
                         CREATE TABLE IF NOT EXISTS user_hidden_subjects
                         (
                             user_key TEXT,
                             group_id INTEGER,
                             subject_name TEXT,
                             PRIMARY KEY (user_key, group_id, subject_name)
                             )
                         ''')
        await db.commit()


async def get_group(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT group_name, group_id FROM user_groups WHERE user_key = ?",
                              (str(user_id),)) as cursor:
            row = await cursor.fetchone()
            return {"group_name": row[0], "group_id": row[1]} if row else None


async def set_group(user_id: int, group_name: str, group_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO user_groups (user_key, group_name, group_id) VALUES (?, ?, ?)",
                         (str(user_id), group_name, group_id))
        await db.commit()


async def get_chat_group(chat_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT group_name, group_id FROM chat_groups WHERE chat_id = ?",
                              (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return {"group_name": row[0], "group_id": row[1]} if row else None


async def set_chat_group(chat_id: int, group_name: str, group_id: int, set_by: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO chat_groups (chat_id, group_name, group_id, set_by) VALUES (?, ?, ?, ?)",
            (chat_id, group_name, group_id, set_by))
        await db.commit()


async def delete_chat_group(chat_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM chat_groups WHERE chat_id = ?", (chat_id,))
        await db.commit()


async def migrate_chat_group(old_chat_id: int, new_chat_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE OR REPLACE chat_groups SET chat_id = ? WHERE chat_id = ?",
                         (new_chat_id, old_chat_id))
        await db.commit()


async def get_chats_for_group(group_id: int) -> list[int]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT chat_id FROM chat_groups WHERE group_id = ?", (group_id,)) as cursor:
            return [r[0] for r in await cursor.fetchall()]


def is_group_chat(chat) -> bool:
    return chat.type in ("group", "supergroup")


async def resolve_group(user_id: int, chat):
    if is_group_chat(chat):
        return await get_chat_group(chat.id)
    return await get_group(user_id)


async def get_hidden_subjects(user_id: int, group_id: int) -> set[str]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                "SELECT subject_name FROM user_hidden_subjects WHERE user_key = ? AND group_id = ?",
                (str(user_id), group_id)
        ) as cursor:
            rows = await cursor.fetchall()
            return {r[0] for r in rows}


async def toggle_hidden_subject(user_id: int, group_id: int, subject_name: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                "SELECT 1 FROM user_hidden_subjects WHERE user_key = ? AND group_id = ? AND subject_name = ?",
                (str(user_id), group_id, subject_name)
        ) as cursor:
            exists = await cursor.fetchone()

        if exists:
            await db.execute(
                "DELETE FROM user_hidden_subjects WHERE user_key = ? AND group_id = ? AND subject_name = ?",
                (str(user_id), group_id, subject_name)
            )
            await db.commit()
            return False
        else:
            await db.execute(
                "INSERT INTO user_hidden_subjects (user_key, group_id, subject_name) VALUES (?, ?, ?)",
                (str(user_id), group_id, subject_name)
            )
            await db.commit()
            return True


async def get_link(user_id: int, group_id: int, subject: str, pair_type: str,
                   include_shared: bool = False) -> str | None:
    owners = (user_id, 0) if include_shared else (user_id,)
    marks = ",".join("?" * len(owners))
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
                f"SELECT url FROM subject_links "
                f"WHERE group_id = ? AND subject_name = ? AND pair_type = ? AND owner_id IN ({marks}) "
                f"ORDER BY owner_id DESC LIMIT 1",
                (group_id, subject, pair_type, *owners)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_link(user_id: int, group_id: int, subject: str, pair_type: str,
                   url: str, shared: bool = False):
    owner = 0 if shared else user_id
    async with aiosqlite.connect(DB_NAME) as db:
        if url == "-":
            await db.execute(
                "DELETE FROM subject_links WHERE group_id = ? AND subject_name = ? "
                "AND pair_type = ? AND owner_id = ?",
                (group_id, subject, pair_type, owner))
        else:
            await db.execute(
                "INSERT OR REPLACE INTO subject_links "
                "(group_id, subject_name, pair_type, owner_id, url, set_by) VALUES (?, ?, ?, ?, ?, ?)",
                (group_id, subject, pair_type, owner, url, user_id))
        await db.commit()