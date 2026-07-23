from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.dependencies import ThreadManagerDep
from app.schemas import CreateThreadResponse, MessageRecord, ThreadSummary
from app.services.thread_manager import ThreadNotFoundError
from app.services.thread_models import preview_thread_title

router = APIRouter(prefix="/threads", tags=["threads"])


@router.get("", response_model=list[ThreadSummary])
def list_threads(threads: ThreadManagerDep) -> list[ThreadSummary]:
    return [
        ThreadSummary(
            thread_id=thread.thread_id,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            message_count=(
                thread.message_count if thread.message_count is not None else len(thread.messages)
            ),
            title=thread.title
            or preview_thread_title(thread.messages),
        )
        for thread in threads.list_threads()
    ]


@router.post("", response_model=CreateThreadResponse, status_code=201)
def create_thread(threads: ThreadManagerDep) -> CreateThreadResponse:
    thread = threads.create_thread()
    return CreateThreadResponse(thread_id=thread.thread_id, created_at=thread.created_at)


@router.get("/{thread_id}/messages", response_model=list[MessageRecord])
def get_thread_messages(thread_id: str, threads: ThreadManagerDep) -> list[MessageRecord]:
    try:
        messages = threads.get_messages(thread_id)
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [
        MessageRecord(
            message_id=message.message_id,
            thread_id=message.thread_id,
            role=message.role,
            content=message.content,
            metadata=message.metadata,
            created_at=message.created_at,
        )
        for message in messages
    ]
