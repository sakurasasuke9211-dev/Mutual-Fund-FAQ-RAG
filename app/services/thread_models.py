from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


class ThreadNotFoundError(Exception):
    """Raised when a thread ID does not exist."""


@dataclass
class StoredMessage:
    message_id: str
    thread_id: str
    role: Literal["user", "assistant"]
    content: str
    metadata: dict[str, Any]
    created_at: datetime


@dataclass
class StoredThread:
    thread_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[StoredMessage] = field(default_factory=list)
    message_count: int | None = None
