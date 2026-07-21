from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ingestion.embedder import DeterministicEmbeddingProvider, EmbeddingConfig, EmbeddingService
from ingestion.models import VectorStoreConfig
from ingestion.vector_store import VectorSearchHit, VectorStore
from rag.config import load_rag_config
from rag.models import RAGConfig
from rag.pipeline import RAGPipeline
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.reranker import PassthroughReranker


def _metadata(
    *,
    scheme_name: str,
    section_id: str,
    source_url: str,
    answer_mode: str = "factual",
) -> dict[str, str | int]:
    return {
        "source_url": source_url,
        "source_domain": "groww.in",
        "document_type": "scheme_page",
        "amc_name": "HDFC Mutual Fund",
        "scheme_name": scheme_name,
        "scheme_category": "elss" if "ELSS" in scheme_name else "large-cap",
        "section_id": section_id,
        "section_title": section_id.replace("_", " ").title(),
        "answer_mode": answer_mode,
        "last_fetched_at": "2026-07-16",
        "content_hash": "hash123",
        "language": "en",
        "token_count": 40,
        "document_id": "doc-1",
        "chunk_index": 0,
    }


@pytest.fixture
def corpus_records() -> list[VectorSearchHit]:
    elss_url = "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth"
    large_cap_url = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
    return [
        VectorSearchHit(
            chunk_id="elss-expense",
            text=(
                "Scheme: HDFC ELSS Tax Saver Fund – Direct Plan Growth\n"
                "Section: Fees & Loads\n\nExpense Ratio: 1.18%"
            ),
            metadata=_metadata(
                scheme_name="HDFC ELSS Tax Saver Fund – Direct Plan Growth",
                section_id="fees_and_loads",
                source_url=elss_url,
            ),
            dense_score=0.0,
        ),
        VectorSearchHit(
            chunk_id="elss-lockin",
            text=(
                "Scheme: HDFC ELSS Tax Saver Fund – Direct Plan Growth\n"
                "Section: Fund Details\n\nLock-in Period: 3 years"
            ),
            metadata=_metadata(
                scheme_name="HDFC ELSS Tax Saver Fund – Direct Plan Growth",
                section_id="fund_details",
                source_url=elss_url,
            ),
            dense_score=0.0,
        ),
        VectorSearchHit(
            chunk_id="large-cap-expense",
            text=(
                "Scheme: HDFC Large Cap Fund – Direct Growth\n"
                "Section: Fees & Loads\n\nExpense Ratio: 0.97%"
            ),
            metadata=_metadata(
                scheme_name="HDFC Large Cap Fund – Direct Growth",
                section_id="fees_and_loads",
                source_url=large_cap_url,
            ),
            dense_score=0.0,
        ),
    ]


@pytest.fixture
def rag_config(tmp_path, monkeypatch) -> RAGConfig:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config_path = tmp_path / "rag.yaml"
    config_path.write_text(
        "rag:\n"
        "  retrieval:\n"
        "    dense_top_k: 3\n"
        "    sparse_top_k: 3\n"
        "    hybrid_alpha: 0.5\n"
        "    final_top_k: 2\n"
        "    reranker_enabled: false\n"
        "    reranker_model: cross-encoder/ms-marco-MiniLM-L-6-v2\n"
        "    min_rerank_score: -10\n"
        "  generation:\n"
        "    provider: template\n"
        "    model: template-local\n"
        "    temperature: 0.0\n"
        "    max_sentences: 3\n"
        "    max_tokens: 128\n"
        "    request_timeout_seconds: 5\n",
        encoding="utf-8",
    )
    return load_rag_config(config_path)


@pytest.fixture
def embedding_service() -> EmbeddingService:
    config = EmbeddingConfig(
        provider="local",
        model="deterministic-local",
        dimensions=32,
        batch_size=8,
        normalize=True,
        max_retries=1,
        retry_delay_seconds=0,
        query_prefix="query: ",
    )
    return EmbeddingService(config=config, provider=DeterministicEmbeddingProvider(dimensions=32))


@pytest.fixture
def mock_vector_store(corpus_records: list[VectorSearchHit]) -> VectorStore:
    store = VectorStore.__new__(VectorStore)
    store.config = VectorStoreConfig(
        provider="chroma_local",
        collection_name="test",
        cloud_host="api.trychroma.com",
        cloud_port=443,
    )

    def search(query_embedding, *, n_results=10, where=None):
        records = corpus_records
        if where:
            records = [
                record
                for record in records
                if all(str(record.metadata.get(key, "")) == str(value) for key, value in where.items())
            ]
        ranked = sorted(records, key=lambda record: sum(query_embedding[:3]), reverse=True)
        hits: list[VectorSearchHit] = []
        for index, record in enumerate(ranked[:n_results]):
            hits.append(
                VectorSearchHit(
                    chunk_id=record.chunk_id,
                    text=record.text,
                    metadata=record.metadata,
                    dense_score=1.0 - (index * 0.1),
                )
            )
        return hits

    store.search = MagicMock(side_effect=search)
    store.list_all = MagicMock(return_value=corpus_records)
    return store


def test_hybrid_retriever_returns_elss_expense_chunk(
    rag_config: RAGConfig,
    embedding_service: EmbeddingService,
    mock_vector_store: VectorStore,
    corpus_records: list[VectorSearchHit],
) -> None:
    retriever = HybridRetriever(
        config=rag_config.retrieval,
        embedding_service=embedding_service,
        vector_store=mock_vector_store,
        reranker=PassthroughReranker(),
        corpus_records=corpus_records,
    )

    chunks = retriever.retrieve("What is the expense ratio of HDFC ELSS Tax Saver Fund?")

    assert chunks
    assert chunks[0].chunk_id == "elss-expense"
    assert "Expense Ratio" in chunks[0].text


def test_rag_pipeline_end_to_end(
    rag_config: RAGConfig,
    embedding_service: EmbeddingService,
    mock_vector_store: VectorStore,
    corpus_records: list[VectorSearchHit],
) -> None:
    retriever = HybridRetriever(
        config=rag_config.retrieval,
        embedding_service=embedding_service,
        vector_store=mock_vector_store,
        reranker=PassthroughReranker(),
        corpus_records=corpus_records,
    )
    pipeline = RAGPipeline(config=rag_config, retriever=retriever, guardrails_enabled=False)

    result = pipeline.answer("What is the expense ratio of HDFC ELSS Tax Saver Fund?")

    assert "Expense Ratio is 1.18%" in result.answer
    assert result.citation.source_url == "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth"
    assert result.chunk_ids[0] == "elss-expense"


def test_rag_pipeline_guarded_allows_factual_query(
    rag_config: RAGConfig,
    embedding_service: EmbeddingService,
    mock_vector_store: VectorStore,
    corpus_records: list[VectorSearchHit],
) -> None:
    retriever = HybridRetriever(
        config=rag_config.retrieval,
        embedding_service=embedding_service,
        vector_store=mock_vector_store,
        reranker=PassthroughReranker(),
        corpus_records=corpus_records,
    )
    pipeline = RAGPipeline(config=rag_config, retriever=retriever, guardrails_enabled=True)

    guarded = pipeline.answer_guarded("What is the expense ratio of HDFC ELSS Tax Saver Fund?")

    assert guarded.response_type == "answer"
    assert "Expense Ratio is 1.18%" in guarded.answer
