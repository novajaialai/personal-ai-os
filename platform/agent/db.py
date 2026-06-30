import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path("/state/sessions.db")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id       TEXT PRIMARY KEY,
                title    TEXT,
                mode     TEXT DEFAULT 'second_brain',
                created_at INTEGER,
                updated_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
        """)


def create_session(title: str = "", mode: str = "second_brain") -> str:
    sid = str(uuid.uuid4())
    now = int(time.time())
    with _conn() as c:
        c.execute(
            "INSERT INTO sessions (id, title, mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (sid, title, mode, now, now),
        )
    return sid


def update_session_title(session_id: str, title: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
            (title, int(time.time()), session_id),
        )


def touch_session(session_id: str) -> None:
    with _conn() as c:
        c.execute("UPDATE sessions SET updated_at=? WHERE id=?", (int(time.time()), session_id))


def save_message(session_id: str, role: str, content: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, int(time.time())),
        )


def get_messages(session_id: str, limit: int = 20) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def list_sessions() -> list[dict]:
    with _conn() as c:
        rows = c.execute("""
            SELECT s.id, s.title, s.mode, s.created_at, s.updated_at,
                   COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_session_detail(session_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return None
        msgs = c.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    return {"session": dict(row), "messages": [dict(m) for m in msgs]}


def session_exists(session_id: str) -> bool:
    with _conn() as c:
        return bool(c.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone())
