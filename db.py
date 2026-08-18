import aiosqlite

from config import DB_NAME

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
                         CREATE TABLE IF NOT EXISTS subject_links
                         (
                             group_id INTEGER,
                             subject_name TEXT,
                             pair_type TEXT,
                             url TEXT,
                             PRIMARY KEY (group_id, subject_name, pair_type)
                             )
                         ''')
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


async def get_link(group_id: int, subject: str, pair_type: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT url FROM subject_links WHERE group_id = ? AND subject_name = ? AND pair_type = ?",
                              (group_id, subject, pair_type)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_link(group_id: int, subject: str, pair_type: str, url: str):
    async with aiosqlite.connect(DB_NAME) as db:
        if url == "-":
            await db.execute("DELETE FROM subject_links WHERE group_id = ? AND subject_name = ? AND pair_type = ?",
                             (group_id, subject, pair_type))
        else:
            await db.execute(
                "INSERT OR REPLACE INTO subject_links (group_id, subject_name, pair_type, url) VALUES (?, ?, ?, ?)",
                (group_id, subject, pair_type, url))
        await db.commit()
