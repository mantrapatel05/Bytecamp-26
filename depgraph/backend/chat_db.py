import sqlite3
import uuid
import datetime
from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parent.parent / "chat_history.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id       TEXT PRIMARY KEY,
            title    TEXT NOT NULL,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            timestamp  TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        )
    """)
    conn.commit()
    conn.close()


def create_session(username: str, title: str = "New Chat") -> dict:
    conn = get_db()
    session_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO chat_sessions (id, title, username, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, title, username, now, now),
    )
    conn.commit()
    conn.close()
    return {"id": session_id, "title": title, "username": username,
            "created_at": now, "updated_at": now}


def save_message(session_id: str, role: str, content: str) -> dict:
    conn = get_db()
    msg_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        (msg_id, session_id, role, content, now),
    )
    conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now, session_id))
    conn.commit()
    conn.close()
    return {"id": msg_id, "session_id": session_id, "role": role,
            "content": content, "timestamp": now}


def update_session_title(session_id: str, title: str):
    conn = get_db()
    conn.execute("UPDATE chat_sessions SET title=? WHERE id=?", (title, session_id))
    conn.commit()
    conn.close()


def get_sessions(username: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at FROM chat_sessions "
        "WHERE username=? ORDER BY updated_at DESC",
        (username,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_messages(session_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, role, content, timestamp FROM chat_messages "
        "WHERE session_id=? ORDER BY timestamp ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_session(session_id: str):
    conn = get_db()
    conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()
