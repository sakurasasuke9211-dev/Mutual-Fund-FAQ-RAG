from __future__ import annotations

from typing import Any, Literal

from app.config import load_api_config
from app.services.thread_models import StoredMessage, StoredThread, ThreadNotFoundError
from app.services.thread_store import InMemoryThreadStore, ThreadStore, build_thread_store

__all__ = [
    "StoredMessage",
    "StoredThread",
    "ThreadManager",
    "ThreadNotFoundError",
    "build_thread_manager",
]


class ThreadManager:
    """Thread-scoped message history (§7). Delegates to memory or SQLite store."""

    def __init__(self, store: ThreadStore | None = None) -> None:
        self._store = store or InMemoryThreadStore()

    def create_thread(self) -> StoredThread:
        return self._store.create_thread()

    def list_threads(self) -> list[StoredThread]:
        return self._store.list_threads()

    def get_thread(self, thread_id: str) -> StoredThread:
        return self._store.get_thread(thread_id)

    def add_message(
        self,
        thread_id: str,
        *,
        role: Literal["user", "assistant"],
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredMessage:
        return self._store.add_message(
            thread_id,
            role=role,
            content=content,
            metadata=metadata,
        )

    def get_messages(self, thread_id: str) -> list[StoredMessage]:
        return self._store.get_messages(thread_id)

    def get_recent_messages(self, thread_id: str, *, max_turns: int) -> list[StoredMessage]:
        messages = self.get_messages(thread_id)
        if max_turns <= 0:
            return []
        return messages[-(max_turns * 2) :]


def build_thread_manager() -> ThreadManager:
    api_config = load_api_config()
    store = build_thread_store(
        backend=api_config.thread_store,
        db_path=api_config.thread_db_path,
    )
    return ThreadManager(store=store)
