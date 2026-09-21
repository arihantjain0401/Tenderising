"""Chat conversation store — sessions + messages in a standalone sqlite file.

Kept out of the curated procurement DB (data/curated.db) so chat state never
mixes with procurement data. Mirrors the standalone data/rag_index.sqlite
pattern: stdlib ``sqlite3``, tables created on first use.

Only *user* and *assistant final-answer* messages are persisted; per-turn tool
results are regenerated each request (the standard agent-loop pattern). Each
message records the provider/model that produced it so answers are attributable.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tenderising.config import CHAT_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT,
    provider TEXT,
    model TEXT,
    user_id TEXT,
    widgets TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    role TEXT,
    content TEXT,
    tool_rounds TEXT,
    provider TEXT,
    model TEXT,
    ip TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _connect(db_path=None) -> sqlite3.Connection:
    path = str(db_path or CHAT_DB_PATH)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    # Migrate pre-existing tables that predate the provider/model/user/widget columns.
    mcols = {row[1] for row in con.execute("PRAGMA table_info(messages)")}
    if "provider" not in mcols:
        con.execute("ALTER TABLE messages ADD COLUMN provider TEXT")
    if "model" not in mcols:
        con.execute("ALTER TABLE messages ADD COLUMN model TEXT")
    if "ip" not in mcols:
        con.execute("ALTER TABLE messages ADD COLUMN ip TEXT")
    scols = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
    if "user_id" not in scols:
        con.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")
    if "widgets" not in scols:
        con.execute("ALTER TABLE sessions ADD COLUMN widgets TEXT")
    return con


def create_session(
    provider: str | None = None,
    model: str | None = None,
    user_id: str | None = None,
    db_path=None,
) -> str:
    """Create a new empty session and return its id."""
    sid = uuid.uuid4().hex
    now = _now()
    con = _connect(db_path)
    try:
        con.execute(
            "INSERT INTO sessions (id, title, provider, model, user_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, None, provider, model, user_id, now, now),
        )
        con.commit()
    finally:
        con.close()
    return sid


def list_sessions(user_id: str | None = None, db_path=None) -> list[dict]:
    """All sessions, newest first. When ``user_id`` is given, only that user's."""
    con = _connect(db_path)
    try:
        if user_id is not None:
            rows = con.execute(
                "SELECT id, title, provider, model, created_at, updated_at FROM sessions "
                "WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, title, provider, model, created_at, updated_at "
                "FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
    finally:
        con.close()
    return [
        {
            "id": r[0],
            "title": r[1],
            "provider": r[2],
            "model": r[3],
            "created_at": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]


def get_session(session_id: str, db_path=None) -> dict | None:
    """One session with its messages and widget snapshot, or None."""
    con = _connect(db_path)
    try:
        row = con.execute(
            "SELECT id, title, provider, model, user_id, widgets, created_at, updated_at "
            "FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        widgets = None
        if row[5]:
            try:
                widgets = json.loads(row[5])
            except json.JSONDecodeError:
                widgets = []
        return {
            "id": row[0],
            "title": row[1],
            "provider": row[2],
            "model": row[3],
            "user_id": row[4],
            "widgets": widgets,
            "created_at": row[6],
            "updated_at": row[7],
        }
    finally:
        con.close()


def set_widgets(session_id: str, widgets: list[dict], db_path=None) -> None:
    """Replace the session's widget snapshot."""
    con = _connect(db_path)
    try:
        con.execute(
            "UPDATE sessions SET widgets = ?, updated_at = ? WHERE id = ?",
            (json.dumps(widgets, default=str), _now(), session_id),
        )
        con.commit()
    finally:
        con.close()


def get_messages(session_id: str, db_path=None) -> list[dict]:
    """Messages for one session, chronological."""
    con = _connect(db_path)
    try:
        rows = con.execute(
            "SELECT role, content, tool_rounds, provider, model, ip, created_at FROM messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    finally:
        con.close()
    out = []
    for role, content, tool_rounds, provider, model, ip, created_at in rows:
        tr = None
        if tool_rounds:
            try:
                tr = json.loads(tool_rounds)
            except json.JSONDecodeError:
                tr = []
        out.append(
            {
                "role": role,
                "content": content,
                "tool_rounds": tr,
                "provider": provider,
                "model": model,
                "ip": ip,
                "created_at": created_at,
            }
        )
    return out


def add_message(
    session_id: str,
    role: str,
    content: str,
    tool_rounds: list[dict] | None = None,
    provider: str | None = None,
    model: str | None = None,
    ip: str | None = None,
    db_path=None,
) -> None:
    """Append a message and bump the session's ``updated_at``.

    The first non-empty user message also becomes the session title (truncated)
    and stamps the session's provider/model, so the sidebar shows a meaningful
    title and the model that drove the conversation.
    """
    now = _now()
    con = _connect(db_path)
    try:
        con.execute(
            "INSERT INTO messages "
            "(session_id, role, content, tool_rounds, provider, model, ip, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                json.dumps(tool_rounds, default=str) if tool_rounds else None,
                provider,
                model,
                ip,
                now,
            ),
        )
        if role == "user" and content.strip():
            title = content.strip().replace("\n", " ")[:48]
            con.execute(
                "UPDATE sessions SET title = COALESCE(title, ?), "
                "provider = COALESCE(provider, ?), model = COALESCE(model, ?), "
                "updated_at = ? WHERE id = ?",
                (title, provider, model, now, session_id),
            )
        else:
            con.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
        con.commit()
    finally:
        con.close()


def delete_session(session_id: str, db_path=None) -> None:
    con = _connect(db_path)
    try:
        con.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        con.commit()
    finally:
        con.close()
