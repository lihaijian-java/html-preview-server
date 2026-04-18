import aiosqlite
from datetime import datetime
from pathlib import Path
from config import DB_PATH

CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    owner       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    expires_at  TEXT,
    password    TEXT,
    visit_count INTEGER DEFAULT 0,
    entry_file  TEXT DEFAULT 'index.html',
    original_filename TEXT,
    file_count  INTEGER DEFAULT 0,
    total_size  INTEGER DEFAULT 0,
    updated_at  TEXT
);
"""


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS_TABLE_SQL)
        await db.execute(CREATE_TABLE_SQL)
        migrations = [
            "ALTER TABLE projects ADD COLUMN owner TEXT",
            "ALTER TABLE projects ADD COLUMN entry_file TEXT DEFAULT 'index.html'",
            "ALTER TABLE projects ADD COLUMN original_filename TEXT",
            "ALTER TABLE projects ADD COLUMN file_count INTEGER DEFAULT 0",
            "ALTER TABLE projects ADD COLUMN total_size INTEGER DEFAULT 0",
            "ALTER TABLE projects ADD COLUMN updated_at TEXT",
        ]
        for sql in migrations:
            try:
                await db.execute(sql)
            except Exception:
                pass
        await db.commit()


async def create_project(project_id: str, name: str, owner: str | None = None,
                         password: str | None = None,
                         expires_at: str | None = None,
                         entry_file: str = "index.html",
                         original_filename: str | None = None,
                         file_count: int = 0,
                         total_size: int = 0) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO projects
            (id, name, owner, password, expires_at, entry_file, original_filename, file_count, total_size, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            """,
            (project_id, name, owner, password, expires_at, entry_file, original_filename, file_count, total_size)
        )
        await db.commit()
    return await get_project(project_id)


async def get_project(project_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


async def list_projects(owner: str | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if owner:
            cursor = await db.execute(
                "SELECT * FROM projects WHERE owner = ? ORDER BY created_at DESC",
                (owner,)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM projects ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_project(project_id: str, **fields) -> dict | None:
    allowed = {"name", "password", "expires_at", "id", "owner", "entry_file", "original_filename", "file_count", "total_size"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}

    # 空字符串表示清除（password 已由上游处理，expires_at 保留原逻辑）
    if "password" in fields and fields["password"] == "":
        updates["password"] = None
    if "expires_at" in fields and fields["expires_at"] == "":
        updates["expires_at"] = None

    if not updates:
        return await get_project(project_id)

    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [project_id]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE projects SET {set_clause} WHERE id = ?", values
        )
        await db.commit()

    new_id = updates.get("id", project_id)
    return await get_project(new_id)


async def delete_project(project_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()
        return cursor.rowcount > 0


async def increment_visit(project_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET visit_count = visit_count + 1 WHERE id = ?",
            (project_id,)
        )
        await db.commit()


# ── 用户管理 ──────────────────────────────────────────────

async def get_user(username: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def user_exists(username: str) -> bool:
    return await get_user(username) is not None


async def create_user(username: str, password_hash: str, salt: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, password_hash, salt)
        )
        await db.commit()
    return await get_user(username)


async def update_user_password(username: str, password_hash: str, salt: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
            (password_hash, salt, username)
        )
        await db.commit()
        return cursor.rowcount > 0
