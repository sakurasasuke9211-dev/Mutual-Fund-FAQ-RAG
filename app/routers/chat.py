from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.dependencies import APIConfigDep, PipelineDep, ThreadManagerDep
from app.schemas import ChatRequest, ChatResponse, EducationalLinkResponse
from app.services.context import build_effective_query
from app.services.thread_manager import ThreadNotFoundError
from guardrails.models import GuardedResponse

router = APIRouter(tags=["chat"])


def _to_chat_response(thread_id: str, guarded: GuardedResponse) -> ChatResponse:
    educational = None
    if guarded.educational_link is not None:
        educational = EducationalLinkResponse(
            label=guarded.educational_link.label,
            url=guarded.educational_link.url,
        )
    return ChatResponse(
        thread_id=thread_id,
        answer=guarded.answer,
        source_url=guarded.source_url,
        source_title=guarded.source_title,
        last_updated=guarded.last_updated,
        response_type=guarded.response_type,
        educational_link=educational,
        chunk_ids=list(guarded.chunk_ids or []),
    )


@router.post("/chat", response_model=ChatResponse)
def post_chat(
    payload: ChatRequest,
    pipeline: PipelineDep,
    threads: ThreadManagerDep,
    api_config: APIConfigDep,
) -> ChatResponse:
    try:
        threads.get_thread(payload.thread_id)
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    recent = threads.get_recent_messages(
        payload.thread_id,
        max_turns=api_config.max_context_turns,
    )
    effective_query, metadata_filters = build_effective_query(payload.query, recent)

    threads.add_message(
        payload.thread_id,
        role="user",
        content=payload.query.strip(),
    )

    guarded = pipeline.answer_guarded(effective_query, metadata_filters=metadata_filters)

    assistant_metadata = {
        "response_type": guarded.response_type,
        "source_url": guarded.source_url,
        "source_title": guarded.source_title,
        "last_updated": guarded.last_updated,
        "chunk_ids": guarded.chunk_ids or [],
        "scheme_name": guarded.source_title,
        "query_reason": guarded.query_reason,
        "refusal_category": guarded.refusal_category,
    }
    if guarded.educational_link is not None:
        assistant_metadata["educational_link"] = {
            "label": guarded.educational_link.label,
            "url": guarded.educational_link.url,
        }

    threads.add_message(
        payload.thread_id,
        role="assistant",
        content=guarded.answer,
        metadata=assistant_metadata,
    )

    return _to_chat_response(payload.thread_id, guarded)
