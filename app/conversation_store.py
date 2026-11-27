from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.settings import PROJECT_ROOT

STATE_DB_PATH = PROJECT_ROOT / "data" / "agent_state.sqlite3"
HISTORY_LIMIT = 8


class ConversationStore:
    """Persist chat turns separately from the read-only Olist analytics database."""

    def __init__(self, database_path: Path = STATE_DB_PATH) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session_id "
                "ON messages(session_id, message_id)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        now = self._now()
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO sessions(session_id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
        return session_id

    def exists(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row is not None

    def history(self, session_id: str) -> list[dict[str, str]]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT role, content FROM messages
                WHERE session_id = ?
                ORDER BY message_id DESC
                LIMIT ?
                """,
                (session_id, HISTORY_LIMIT),
            ).fetchall()
        return [
            {"role": role, "content": content}
            for role, content in reversed(rows)
        ]

    def save_turn(self, session_id: str, question: str, answer: str) -> None:
        now = self._now()
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO messages(session_id, role, content, created_at) "
                "VALUES (?, 'user', ?, ?)",
                (session_id, question, now),
            )
            connection.execute(
                "INSERT INTO messages(session_id, role, content, created_at) "
                "VALUES (?, 'assistant', ?, ?)",
                (session_id, answer, now),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )

    def messages(self, session_id: str) -> list[dict[str, str]]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT role, content, created_at FROM messages
                WHERE session_id = ? ORDER BY message_id
                """,
                (session_id,),
            ).fetchall()
        return [
            {"role": role, "content": content, "created_at": created_at}
            for role, content, created_at in rows
        ]
