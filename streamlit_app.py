from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

import streamlit as st

from app.services.context import build_effective_query
from app.services.thread_models import StoredMessage
from ingestion.config import load_env_file
from rag.pipeline import RAGPipeline


def _apply_streamlit_secrets() -> None:
    """Copy Streamlit Cloud secrets into process env for existing config loaders."""
    try:
        secrets = st.secrets
    except Exception:
        return

    for key in (
        "CHROMA_API_KEY",
        "CHROMA_TENANT",
        "CHROMA_DATABASE",
        "CHROMA_COLLECTION_NAME",
        "VECTOR_STORE_PROVIDER",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
    ):
        try:
            value = secrets.get(key)
        except Exception:
            value = None
        if value is not None and str(value).strip():
            os.environ[key] = str(value).strip()


@dataclass
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@st.cache_resource(show_spinner="Loading FundFacts RAG pipeline…")
def get_pipeline() -> RAGPipeline:
    load_env_file()
    _apply_streamlit_secrets()
    os.environ.setdefault("VECTOR_STORE_PROVIDER", "chroma_cloud")
    os.environ.setdefault("LLM_PROVIDER", "groq")
    return RAGPipeline()


def _history_as_messages(turns: list[ChatTurn]) -> list[StoredMessage]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    messages: list[StoredMessage] = []
    for index, turn in enumerate(turns):
        messages.append(
            StoredMessage(
                message_id=f"streamlit-{index}",
                thread_id="streamlit-session",
                role=turn.role,
                content=turn.content,
                metadata=turn.metadata,
                created_at=now,
            )
        )
    return messages


def main() -> None:
    st.set_page_config(
        page_title="FundFacts FAQ",
        layout="centered",
    )
    _apply_streamlit_secrets()

    st.title("FundFacts FAQ")
    st.caption(
        "Factual mutual-fund answers from Groww scheme pages. "
        "Not investment advice."
    )
    st.info(
        "This free Streamlit deployment runs the RAG pipeline in-process. "
        "It serves the hosted app URL, not a separate FastAPI REST API."
    )

    if "turns" not in st.session_state:
        st.session_state.turns = []

    for turn in st.session_state.turns:
        with st.chat_message(turn.role):
            st.markdown(turn.content)
            if turn.role == "assistant":
                meta = turn.metadata
                if meta.get("response_type") == "refusal":
                    st.warning("Facts only — this assistant does not give investment advice.")
                    link = meta.get("educational_link")
                    if isinstance(link, dict) and link.get("url"):
                        st.markdown(f"[{link.get('label', 'Learn more')}]({link['url']})")
                elif meta.get("source_url"):
                    title = meta.get("source_title") or "Source"
                    updated = meta.get("last_updated")
                    label = f"Source: {title}"
                    if updated:
                        label += f" (updated {updated})"
                    st.markdown(f"[{label}]({meta['source_url']})")

    prompt = st.chat_input("Ask a factual question about an HDFC scheme…")
    if not prompt:
        return

    st.session_state.turns.append(ChatTurn(role="user", content=prompt.strip()))
    with st.chat_message("user"):
        st.markdown(prompt.strip())

    with st.chat_message("assistant"):
        with st.spinner("Retrieving facts…"):
            try:
                pipeline = get_pipeline()
                recent = _history_as_messages(st.session_state.turns[:-1])
                effective_query, metadata_filters = build_effective_query(
                    prompt,
                    recent,
                )
                guarded = pipeline.answer_guarded(
                    effective_query,
                    metadata_filters=metadata_filters,
                )
            except Exception as exc:  # noqa: BLE001 - surface deploy/runtime errors in UI
                st.error(
                    "The RAG pipeline failed to answer. Check Streamlit secrets "
                    f"(Chroma + Groq) and Cloud resource limits. Details: {exc}"
                )
                st.session_state.turns.pop()
                return

        st.markdown(guarded.answer)
        assistant_metadata: dict[str, Any] = {
            "response_type": guarded.response_type,
            "source_url": guarded.source_url,
            "source_title": guarded.source_title,
            "last_updated": guarded.last_updated,
            "chunk_ids": list(guarded.chunk_ids or []),
            "scheme_name": guarded.source_title,
            "query_reason": guarded.query_reason,
            "refusal_category": guarded.refusal_category,
        }
        if guarded.educational_link is not None:
            assistant_metadata["educational_link"] = {
                "label": guarded.educational_link.label,
                "url": guarded.educational_link.url,
            }
            if guarded.response_type == "refusal":
                st.warning("Facts only — this assistant does not give investment advice.")
                st.markdown(
                    f"[{guarded.educational_link.label}]({guarded.educational_link.url})"
                )
        elif guarded.source_url:
            title = guarded.source_title or "Source"
            updated = guarded.last_updated
            label = f"Source: {title}"
            if updated:
                label += f" (updated {updated})"
            st.markdown(f"[{label}]({guarded.source_url})")

        st.session_state.turns.append(
            ChatTurn(
                role="assistant",
                content=guarded.answer,
                metadata=assistant_metadata,
            )
        )


if __name__ == "__main__":
    main()
