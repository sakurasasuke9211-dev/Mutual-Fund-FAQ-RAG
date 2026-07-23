from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from app.services.thread_models import StoredMessage, StoredThread, ThreadNotFoundError, preview_thread_title


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _dt_from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


class ThreadStore(ABC):
    @abstractmethod
    def create_thread(self) -> StoredThread:
        raise NotImplementedError

    @abstractmethod
    def list_threads(self) -> list[StoredThread]:
        raise NotImplementedError

    @abstractmethod
    def get_thread(self, thread_id: str) -> StoredThread:
        raise NotImplementedError

    @abstractmethod
    def add_message(
        self,
        thread_id: str,
        *,
        role: Literal["user", "assistant"],
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredMessage:
        raise NotImplementedError

    @abstractmethod
    def get_messages(self, thread_id: str) -> list[StoredMessage]:
        raise NotImplementedError


class InMemoryThreadStore(ThreadStore):
    def __init__(self) -> None:
        self._threads: dict[str, StoredThread] = {}
        self._lock = Lock()

    def create_thread(self) -> StoredThread:
        now = _utc_now()
        thread = StoredThread(
            thread_id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            message_count=0,
        )
        with self._lock:
            self._threads[thread.thread_id] = thread
        return thread

    def list_threads(self) -> list[StoredThread]:
        with self._lock:
            threads = list(self._threads.values())
        listed = sorted(threads, key=lambda item: item.updated_at, reverse=True)
        for thread in listed:
            thread.title = preview_thread_title(thread.messages)
            thread.message_count = len(thread.messages)
        return listed

    def get_thread(self, thread_id: str) -> StoredThread:
        with self._lock:
            thread = self._threads.get(thread_id)
        if thread is None:
            raise ThreadNotFoundError(f"Thread not found: {thread_id}")
        return thread

    def add_message(
        self,
        thread_id: str,
        *,
        role: Literal["user", "assistant"],
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredMessage:
        with self._lock:
            thread = self._threads.get(thread_id)
            if thread is None:
                raise ThreadNotFoundError(f"Thread not found: {thread_id}")

            message = StoredMessage(
                message_id=str(uuid.uuid4()),
                thread_id=thread_id,
                role=role,
                content=content,
                metadata=dict(metadata or {}),
                created_at=_utc_now(),
            )
            thread.messages.append(message)
            thread.updated_at = message.created_at
            thread.message_count = len(thread.messages)
            return message

    def get_messages(self, thread_id: str) -> list[StoredMessage]:
        thread = self.get_thread(thread_id)
        return list(thread.messages)


class SqliteThreadStore(ThreadStore):
    """Persistent thread store for dev / shared state across API restarts (§7)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS threads (
                        thread_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS messages (
                        message_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_messages_thread_created
                        ON messages(thread_id, created_at);
                    """
                )

    def create_thread(self) -> StoredThread:
        now = _utc_now()
        thread = StoredThread(
            thread_id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            message_count=0,
        )
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO threads (thread_id, created_at, updated_at) VALUES (?, ?, ?)",
                    (thread.thread_id, _dt_to_iso(thread.created_at), _dt_to_iso(thread.updated_at)),
                )
        return thread

    def list_threads(self) -> list[StoredThread]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        t.thread_id,
                        t.created_at,
                        t.updated_at,
                        COUNT(m.message_id) AS message_count,
                        (
                            SELECT content
                            FROM messages first_user
                            WHERE first_user.thread_id = t.thread_id
                              AND first_user.role = 'user'
                            ORDER BY first_user.created_at ASC
                            LIMIT 1
                        ) AS first_user_content
                    FROM threads t
                    LEFT JOIN messages m ON m.thread_id = t.thread_id
                    GROUP BY t.thread_id, t.created_at, t.updated_at
                    ORDER BY t.updated_at DESC
                    """
                ).fetchall()

        result: list[StoredThread] = []
        for row in rows:
            first_user = row["first_user_content"]
            title = (
                preview_thread_title(
                    [
                        StoredMessage(
                            message_id="preview",
                            thread_id=str(row["thread_id"]),
                            role="user",
                            content=str(first_user),
                            metadata={},
                            created_at=_dt_from_iso(str(row["created_at"])),
                        )
                    ]
                )
                if first_user
                else "New conversation"
            )
            result.append(
                StoredThread(
                    thread_id=str(row["thread_id"]),
                    created_at=_dt_from_iso(str(row["created_at"])),
                    updated_at=_dt_from_iso(str(row["updated_at"])),
                    messages=[],
                    message_count=int(row["message_count"]),
                    title=title,
                )
            )
        return result

    def get_thread(self, thread_id: str) -> StoredThread:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT thread_id, created_at, updated_at FROM threads WHERE thread_id = ?",
                    (thread_id,),
                ).fetchone()
        if row is None:
            raise ThreadNotFoundError(f"Thread not found: {thread_id}")
        return StoredThread(
            thread_id=str(row["thread_id"]),
            created_at=_dt_from_iso(str(row["created_at"])),
            updated_at=_dt_from_iso(str(row["updated_at"])),
            messages=[],
        )

    def add_message(
        self,
        thread_id: str,
        *,
        role: Literal["user", "assistant"],
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredMessage:
        message = StoredMessage(
            message_id=str(uuid.uuid4()),
            thread_id=thread_id,
            role=role,
            content=content,
            metadata=dict(metadata or {}),
            created_at=_utc_now(),
        )
        metadata_json = json.dumps(message.metadata, ensure_ascii=False)

        with self._lock:
            with self._connect() as conn:
                updated = conn.execute(
                    "UPDATE threads SET updated_at = ? WHERE thread_id = ?",
                    (_dt_to_iso(message.created_at), thread_id),
                ).rowcount
                if updated == 0:
                    raise ThreadNotFoundError(f"Thread not found: {thread_id}")

                conn.execute(
                    """
                    INSERT INTO messages
                        (message_id, thread_id, role, content, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.message_id,
                        thread_id,
                        role,
                        content,
                        metadata_json,
                        _dt_to_iso(message.created_at),
                    ),
                )
        return message

    def get_messages(self, thread_id: str) -> list[StoredMessage]:
        self.get_thread(thread_id)
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT message_id, thread_id, role, content, metadata_json, created_at
                    FROM messages
                    WHERE thread_id = ?
                    ORDER BY created_at ASC
                    """,
                    (thread_id,),
                ).fetchall()

        return [
            StoredMessage(
                message_id=str(row["message_id"]),
                thread_id=str(row["thread_id"]),
                role=row["role"],  # type: ignore[arg-type]
                content=str(row["content"]),
                metadata=json.loads(str(row["metadata_json"])),
                created_at=_dt_from_iso(str(row["created_at"])),
            )
            for row in rows
        ]


def build_thread_store(*, backend: str, db_path: Path) -> ThreadStore:
    normalized = backend.strip().lower()
    if normalized == "memory":
        return InMemoryThreadStore()
    if normalized == "sqlite":
        return SqliteThreadStore(db_path)
    raise ValueError(f"Unsupported thread store backend: {backend}")
