import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatHistoryStore:
    def __init__(self, db_path: str):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    channel TEXT NOT NULL DEFAULT 'api',
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    used_docs_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    extra_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_updated ON sessions(user_id, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at ASC)"
            )
            conn.commit()

    def ensure_session(
        self,
        session_id: Optional[str],
        user_id: Optional[str],
        channel: str = "api",
        title_seed: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        sid = (session_id or "").strip() or uuid4().hex
        now = _utc_now()
        title = title_seed.strip()[:80] if title_seed else None
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        with self._write_lock:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT session_id FROM sessions WHERE session_id = ?",
                    (sid,),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE sessions
                        SET user_id = COALESCE(?, user_id),
                            channel = ?,
                            updated_at = ?
                        WHERE session_id = ?
                        """,
                        (user_id, channel, now, sid),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO sessions
                        (session_id, user_id, channel, title, created_at, updated_at, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (sid, user_id, channel, title, now, now, metadata_json),
                    )
                conn.commit()
        return sid

    def touch_session(self, session_id: str) -> None:
        with self._write_lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                    (_utc_now(), session_id),
                )
                conn.commit()

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        used_docs: Optional[List[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        now = _utc_now()
        used_docs_json = json.dumps(used_docs or [], ensure_ascii=False)
        extra_json = json.dumps(extra or {}, ensure_ascii=False)

        with self._write_lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO messages
                    (session_id, role, content, used_docs_json, created_at, extra_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, role, content, used_docs_json, now, extra_json),
                )
                conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                    (now, session_id),
                )
                conn.commit()
                return int(cur.lastrowid)

    def list_sessions(
        self,
        user_id: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        cap = max(1, min(limit, 200))
        where = []
        params: List[Any] = []
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        if channel:
            where.append("channel = ?")
            params.append(channel)

        sql = "SELECT session_id, user_id, channel, title, created_at, updated_at FROM sessions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(cap)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        sid = session_id.strip()
        if not sid:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, user_id, channel, title, created_at, updated_at
                FROM sessions
                WHERE session_id = ?
                """,
                (sid,),
            ).fetchone()
        return dict(row) if row else None

    def list_messages(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        cap = max(1, min(limit, 500))
        skip = max(0, offset)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT message_id, session_id, role, content, used_docs_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY message_id ASC
                LIMIT ? OFFSET ?
                """,
                (session_id, cap, skip),
            ).fetchall()

        messages: List[Dict[str, Any]] = []
        for row in rows:
            used_docs_raw = row["used_docs_json"] or "[]"
            try:
                used_docs = json.loads(used_docs_raw)
            except json.JSONDecodeError:
                used_docs = []
            messages.append(
                {
                    "message_id": row["message_id"],
                    "session_id": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "used_docs": used_docs,
                    "created_at": row["created_at"],
                }
            )
        return messages

    def list_recent_messages(
        self,
        session_id: str,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        cap = max(1, min(limit, 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT message_id, session_id, role, content, used_docs_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY message_id DESC
                LIMIT ?
                """,
                (session_id, cap),
            ).fetchall()

        rows = list(reversed(rows))
        messages: List[Dict[str, Any]] = []
        for row in rows:
            used_docs_raw = row["used_docs_json"] or "[]"
            try:
                used_docs = json.loads(used_docs_raw)
            except json.JSONDecodeError:
                used_docs = []
            messages.append(
                {
                    "message_id": row["message_id"],
                    "session_id": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "used_docs": used_docs,
                    "created_at": row["created_at"],
                }
            )
        return messages
