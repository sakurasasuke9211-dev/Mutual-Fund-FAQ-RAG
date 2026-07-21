from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ThreadSummary(BaseModel):
    thread_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class CreateThreadResponse(BaseModel):
    thread_id: str
    created_at: datetime


class MessageRecord(BaseModel):
    message_id: str
    thread_id: str
    role: Literal["user", "assistant"]
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChatRequest(BaseModel):
    thread_id: str
    query: str = Field(min_length=1, max_length=500)


class EducationalLinkResponse(BaseModel):
    label: str
    url: str


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    source_url: str | None = None
    source_title: str | None = None
    last_updated: str | None = None
    response_type: Literal["answer", "refusal"]
    educational_link: EducationalLinkResponse | None = None
    chunk_ids: list[str] = Field(default_factory=list)
