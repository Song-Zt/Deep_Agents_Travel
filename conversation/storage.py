
"""
会话存储实现。

提供两种后端：
1. JsonFileStorage：一个会话一个 JSON 文件，适合本地调试
2. SQLiteStorage：单文件数据库，适合前端多会话场景
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from conversation.session import (
    ConversationSession,
    ConversationTurn,
    validate_session_id,
)


class JsonFileStorage:
    """一个会话一个 JSON 文件。"""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def _session_path(self, session_id: str) -> Path:
        validate_session_id(session_id)
        return self.directory / f"{session_id}.json"

    def save_session(self, session: ConversationSession):
        path = self._session_path(session.session_id)

        path.parent.mkdir(parents=True, exist_ok=True)

        # 先写临时文件再替换，避免写入中断留下半个 JSON
        temp_path = path.with_suffix(".json.tmp")

        temp_path.write_text(
            json.dumps(
                session.to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temp_path.replace(path)

    def load_session(
        self,
        session_id: str,
    ) -> ConversationSession | None:
        path = self._session_path(session_id)

        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ConversationSession.from_dict(data)

        except (json.JSONDecodeError, ValueError, OSError) as exc:
            print(f"会话加载失败：{session_id}，原因：{exc}")
            return None

    def list_sessions(self) -> list[str]:
        if not self.directory.exists():
            return []

        return sorted(
            path.stem
            for path in self.directory.glob("*.json")
        )

    def delete_session(self, session_id: str) -> bool:
        path = self._session_path(session_id)

        if not path.exists():
            return False

        path.unlink()
        return True


class SQLiteStorage:
    """
    SQLite 会话存储。

    表结构：
    - sessions：会话基本信息
    - messages：每轮消息

    每次写入都用独立连接，避免跨线程共享连接。
    """

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _ensure_schema(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id)
                        REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, id);
                """
            )

    def save_session(self, session: ConversationSession):
        turns = session.turns

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (id, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    metadata = excluded.metadata
                """,
                (
                    session.session_id,
                    session.created_at,
                    session.updated_at,
                    json.dumps(session.metadata, ensure_ascii=False),
                ),
            )

            # 会话会裁剪历史，因此每次整体替换消息，保证数据一致
            connection.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session.session_id,),
            )

            connection.executemany(
                """
                INSERT INTO messages
                    (session_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        session.session_id,
                        turn.role,
                        turn.content,
                        json.dumps(turn.metadata, ensure_ascii=False),
                        turn.created_at,
                    )
                    for turn in turns
                ],
            )

    def load_session(
        self,
        session_id: str,
    ) -> ConversationSession | None:
        validate_session_id(session_id)

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()

            if row is None:
                return None

            message_rows = connection.execute(
                """
                SELECT role, content, metadata, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id
                """,
                (session_id,),
            ).fetchall()

        session = ConversationSession(session_id)

        session.created_at = row["created_at"]
        session.updated_at = row["updated_at"]
        session.metadata = json.loads(row["metadata"] or "{}")
        session.turns = [
            ConversationTurn(
                role=message["role"],
                content=message["content"],
                created_at=message["created_at"],
                metadata=json.loads(message["metadata"] or "{}"),
            )
            for message in message_rows
        ]

        return session

    def list_sessions(self) -> list[str]:
        return [
            item["id"]
            for item in self.list_session_summaries()
        ]

    def list_session_summaries(self) -> list[dict[str, Any]]:
        """返回会话列表，附带标题和消息数量，供前端侧边栏使用。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    s.id,
                    s.created_at,
                    s.updated_at,
                    (SELECT COUNT(*) FROM messages m
                     WHERE m.session_id = s.id) AS message_count,
                    (SELECT m.content FROM messages m
                     WHERE m.session_id = s.id AND m.role = 'user'
                     ORDER BY m.id LIMIT 1) AS title
                FROM sessions s
                ORDER BY s.updated_at DESC, s.rowid DESC
                """
            ).fetchall()

        return [
            {
                "session_id": row["id"],
                "title": (row["title"] or "新会话")[:40],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"],
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        validate_session_id(session_id)

        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,),
            )

            return cursor.rowcount > 0
