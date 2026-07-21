from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from guardrails.models import EducationalLink, GuardedResponse
from rag.pipeline import RAGPipeline


@pytest.fixture
def mock_pipeline() -> MagicMock:
    pipeline = MagicMock(spec=RAGPipeline)
    pipeline.answer_guarded.return_value = GuardedResponse(
        query="What is the expense ratio of HDFC ELSS Tax Saver Fund?",
        response_type="answer",
        answer="For HDFC ELSS Tax Saver Fund – Direct Plan Growth, Expense Ratio is 1.18%.",
        source_url="https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
        source_title="HDFC ELSS Tax Saver Fund – Direct Plan Growth",
        last_updated="2026-07-16",
        chunk_ids=["chunk-1"],
        query_reason="pass",
    )
    return pipeline


@pytest.fixture
def client(mock_pipeline: MagicMock) -> TestClient:
    from app.services.thread_manager import ThreadManager

    app = create_app()
    app.state.thread_manager = ThreadManager()
    app.state.pipeline = mock_pipeline
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cors_allows_local_ui(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_create_thread_and_chat(client: TestClient, mock_pipeline: MagicMock) -> None:
    create = client.post("/threads")
    assert create.status_code == 201
    thread_id = create.json()["thread_id"]

    chat = client.post(
        "/chat",
        json={
            "thread_id": thread_id,
            "query": "What is the expense ratio of HDFC ELSS Tax Saver Fund?",
        },
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["response_type"] == "answer"
    assert body["thread_id"] == thread_id
    assert "groww.in" in body["source_url"]
    mock_pipeline.answer_guarded.assert_called_once()

    messages = client.get(f"/threads/{thread_id}/messages")
    assert messages.status_code == 200
    assert len(messages.json()) == 2


def test_chat_uses_thread_scheme_for_attribute_follow_up(
    client: TestClient,
    mock_pipeline: MagicMock,
) -> None:
    thread_id = client.post("/threads").json()["thread_id"]
    client.post(
        "/chat",
        json={
            "thread_id": thread_id,
            "query": "Tell me about HDFC ELSS Tax Saver Fund",
        },
    )

    response = client.post(
        "/chat",
        json={"thread_id": thread_id, "query": "What is expense ratio?"},
    )

    assert response.status_code == 200
    effective_query = mock_pipeline.answer_guarded.call_args_list[1].args[0]
    metadata_filters = mock_pipeline.answer_guarded.call_args_list[1].kwargs["metadata_filters"]
    assert "HDFC ELSS Tax Saver Fund" in effective_query
    assert metadata_filters == {
        "scheme_name": "HDFC ELSS Tax Saver Fund – Direct Plan Growth"
    }


def test_chat_unknown_thread_returns_404(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={"thread_id": "00000000-0000-0000-0000-000000000000", "query": "Hello"},
    )
    assert response.status_code == 404


def test_chat_refusal(client: TestClient, mock_pipeline: MagicMock) -> None:
    mock_pipeline.answer_guarded.return_value = GuardedResponse(
        query="Should I invest?",
        response_type="refusal",
        answer="I cannot provide investment advice.",
        educational_link=EducationalLink(
            label="AMFI investor education",
            url="https://www.amfiindia.com/investor/knowledge-center",
        ),
        query_reason="advisory",
        refusal_category="advisory",
    )

    thread_id = client.post("/threads").json()["thread_id"]
    response = client.post(
        "/chat",
        json={"thread_id": thread_id, "query": "Should I invest in ELSS?"},
    )
    assert response.status_code == 200
    assert response.json()["response_type"] == "refusal"
    assert response.json()["educational_link"]["url"].startswith("https://")
