from __future__ import annotations

from pathlib import Path

import pytest

from app.services.thread_manager import ThreadManager
from app.services.thread_store import InMemoryThreadStore, SqliteThreadStore


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    return tmp_path / "threads.db"


def test_sqlite_thread_store_persists_across_instances(sqlite_db: Path) -> None:
    store_a = SqliteThreadStore(sqlite_db)
    thread = store_a.create_thread()
    store_a.add_message(thread.thread_id, role="user", content="Hello")
    store_a.add_message(
        thread.thread_id,
        role="assistant",
        content="Hi",
        metadata={"response_type": "answer", "chunk_ids": ["c1"]},
    )

    store_b = SqliteThreadStore(sqlite_db)
    messages = store_b.get_messages(thread.thread_id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].metadata["chunk_ids"] == ["c1"]

    listed = store_b.list_threads()
    assert len(listed) == 1
    assert listed[0].message_count == 2


def test_thread_isolation_between_conversations() -> None:
    manager = ThreadManager(store=InMemoryThreadStore())
    thread_a = manager.create_thread()
    thread_b = manager.create_thread()

    manager.add_message(thread_a.thread_id, role="user", content="Question A")
    manager.add_message(thread_b.thread_id, role="user", content="Question B")

    assert len(manager.get_messages(thread_a.thread_id)) == 1
    assert manager.get_messages(thread_a.thread_id)[0].content == "Question A"
    assert manager.get_messages(thread_b.thread_id)[0].content == "Question B"


def test_get_recent_messages_respects_max_turns() -> None:
    manager = ThreadManager(store=InMemoryThreadStore())
    thread = manager.create_thread()

    for index in range(4):
        manager.add_message(thread.thread_id, role="user", content=f"Q{index}")
        manager.add_message(thread.thread_id, role="assistant", content=f"A{index}")

    recent = manager.get_recent_messages(thread.thread_id, max_turns=2)
    assert len(recent) == 4
    assert recent[0].content == "Q2"
    assert recent[-1].content == "A3"
