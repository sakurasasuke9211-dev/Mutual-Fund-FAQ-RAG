from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from app.services.context import build_effective_query
from app.services.thread_manager import StoredMessage

ELSS = "HDFC ELSS Tax Saver Fund – Direct Plan Growth"
LARGE_CAP = "HDFC Large Cap Fund – Direct Growth"


def _message(
    message_id: str,
    *,
    role: Literal["user", "assistant"],
    content: str,
    scheme_name: str | None = None,
) -> StoredMessage:
    metadata = {}
    if scheme_name:
        metadata = {"scheme_name": scheme_name, "source_title": scheme_name}
    return StoredMessage(
        message_id=message_id,
        thread_id="t1",
        role=role,
        content=content,
        metadata=metadata,
        created_at=datetime.now(timezone.utc),
    )


def test_build_effective_query_uses_thread_scheme_for_follow_up() -> None:
    messages = [
        StoredMessage(
            message_id="m1",
            thread_id="t1",
            role="user",
            content="What is the expense ratio of HDFC ELSS Tax Saver Fund?",
            metadata={},
            created_at=datetime.now(timezone.utc),
        ),
        StoredMessage(
            message_id="m2",
            thread_id="t1",
            role="assistant",
            content="Expense ratio is 1.18%.",
            metadata={
                "scheme_name": "HDFC ELSS Tax Saver Fund – Direct Plan Growth",
                "source_title": "HDFC ELSS Tax Saver Fund – Direct Plan Growth",
            },
            created_at=datetime.now(timezone.utc),
        ),
    ]

    effective_query, filters = build_effective_query("What about its exit load?", messages)

    assert filters == {"scheme_name": "HDFC ELSS Tax Saver Fund – Direct Plan Growth"}
    assert "HDFC ELSS" in effective_query


def test_expense_ratio_uses_current_thread_scheme() -> None:
    messages = [
        _message("m1", role="user", content="Tell me about HDFC ELSS Tax Saver Fund"),
        _message("m2", role="assistant", content="Here are the fund details.", scheme_name=ELSS),
    ]

    effective_query, filters = build_effective_query("What is expense ratio?", messages)

    assert filters == {"scheme_name": ELSS}
    assert effective_query == f"What is expense ratio? ({ELSS})"


def test_explicit_scheme_change_overrides_existing_context() -> None:
    messages = [
        _message("m1", role="user", content="Tell me about HDFC ELSS Tax Saver Fund"),
        _message("m2", role="assistant", content="Here are the fund details.", scheme_name=ELSS),
    ]

    effective_query, filters = build_effective_query(
        "What is the expense ratio of HDFC Large Cap Fund?",
        messages,
    )

    assert filters == {"scheme_name": LARGE_CAP}
    assert effective_query == "What is the expense ratio of HDFC Large Cap Fund?"


def test_latest_user_scheme_change_beats_older_assistant_context() -> None:
    messages = [
        _message("m1", role="assistant", content="ELSS details.", scheme_name=ELSS),
        _message("m2", role="user", content="Now tell me about HDFC Large Cap Fund"),
        _message("m3", role="assistant", content="I could not answer that request."),
    ]

    effective_query, filters = build_effective_query("What is expense ratio?", messages)

    assert filters == {"scheme_name": LARGE_CAP}
    assert LARGE_CAP in effective_query


def test_follow_up_uses_newly_resolved_scheme_context() -> None:
    messages = [
        _message("m1", role="assistant", content="ELSS details.", scheme_name=ELSS),
        _message("m2", role="user", content="Tell me about HDFC Large Cap Fund"),
        _message("m3", role="assistant", content="Large cap details.", scheme_name=LARGE_CAP),
    ]

    effective_query, filters = build_effective_query("What is the benchmark?", messages)

    assert filters == {"scheme_name": LARGE_CAP}
    assert LARGE_CAP in effective_query
