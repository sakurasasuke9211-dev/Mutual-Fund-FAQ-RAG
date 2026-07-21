from __future__ import annotations

import pytest

from citation.models import Citation
from generation.generator import TemplateAnswerGenerator, build_answer_generator
from generation.models import GenerationConfig
from rag.config import load_rag_config
from retrieval.models import RetrievedChunk


@pytest.fixture
def generation_config() -> GenerationConfig:
    return GenerationConfig(
        provider="template",
        model="template-local",
        temperature=0.0,
        max_sentences=3,
        max_tokens=128,
        request_timeout_seconds=5,
    )


@pytest.fixture
def expense_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-expense",
        text=(
            "Scheme: HDFC ELSS Tax Saver Fund – Direct Plan Growth\n"
            "Section: Fees & Loads\n\n"
            "Expense Ratio: 1.18%\n"
            "Exit Load: A fee payable to a mutual fund house"
        ),
        metadata={
            "scheme_name": "HDFC ELSS Tax Saver Fund – Direct Plan Growth",
            "answer_mode": "factual",
            "source_url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
            "last_fetched_at": "2026-07-16",
        },
        dense_score=0.9,
        bm25_score=0.8,
        hybrid_score=0.85,
        rerank_score=1.0,
    )


@pytest.fixture
def performance_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-performance",
        text="Scheme: HDFC ELSS Tax Saver Fund – Direct Plan Growth\nSection: Performance",
        metadata={
            "scheme_name": "HDFC ELSS Tax Saver Fund – Direct Plan Growth",
            "answer_mode": "link_only",
            "source_url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
            "last_fetched_at": "2026-07-16",
        },
        dense_score=0.7,
        bm25_score=0.6,
        hybrid_score=0.65,
        rerank_score=0.5,
    )


def test_template_generator_extracts_expense_ratio(
    generation_config: GenerationConfig,
    expense_chunk: RetrievedChunk,
) -> None:
    generator = TemplateAnswerGenerator(generation_config)
    citation = Citation(
        source_url=str(expense_chunk.metadata["source_url"]),
        source_title=str(expense_chunk.metadata["scheme_name"]),
        last_updated=str(expense_chunk.metadata["last_fetched_at"]),
    )

    answer = generator.generate(
        "What is the expense ratio of HDFC ELSS Tax Saver Fund?",
        [expense_chunk],
        citation,
    )

    assert "Expense Ratio is 1.18%" in answer


def test_template_generator_handles_link_only_performance(
    generation_config: GenerationConfig,
    performance_chunk: RetrievedChunk,
) -> None:
    generator = TemplateAnswerGenerator(generation_config)
    citation = Citation(
        source_url=str(performance_chunk.metadata["source_url"]),
        source_title=str(performance_chunk.metadata["scheme_name"]),
        last_updated=str(performance_chunk.metadata["last_fetched_at"]),
    )

    answer = generator.generate(
        "What are the 1-year returns for this fund?",
        [performance_chunk],
        citation,
    )

    assert "Groww scheme page" in answer
    assert "1.18%" not in answer


def test_build_answer_generator_falls_back_without_api_key(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    config_path = tmp_path / "rag.yaml"
    config_path.write_text(
        "rag:\n"
        "  retrieval:\n"
        "    dense_top_k: 5\n"
        "    sparse_top_k: 5\n"
        "    hybrid_alpha: 0.5\n"
        "    final_top_k: 3\n"
        "    reranker_enabled: false\n"
        "    reranker_model: cross-encoder/ms-marco-MiniLM-L-6-v2\n"
        "    min_rerank_score: -10\n"
        "  generation:\n"
        "    provider: groq\n"
        "    model: llama-3.3-70b-versatile\n"
        "    base_url: https://api.groq.com/openai/v1\n"
        "    temperature: 0.0\n"
        "    max_sentences: 3\n"
        "    max_tokens: 128\n"
        "    request_timeout_seconds: 5\n",
        encoding="utf-8",
    )

    rag_config = load_rag_config(config_path)
    generator = build_answer_generator(rag_config.generation)
    assert isinstance(generator, TemplateAnswerGenerator)


def test_build_answer_generator_uses_groq_when_key_present(
    tmp_path, monkeypatch
) -> None:
    from generation.generator import OpenAICompatibleAnswerGenerator

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    config_path = tmp_path / "rag.yaml"
    config_path.write_text(
        "rag:\n"
        "  retrieval:\n"
        "    dense_top_k: 5\n"
        "    sparse_top_k: 5\n"
        "    hybrid_alpha: 0.5\n"
        "    final_top_k: 3\n"
        "    reranker_enabled: false\n"
        "    reranker_model: cross-encoder/ms-marco-MiniLM-L-6-v2\n"
        "    min_rerank_score: -10\n"
        "  generation:\n"
        "    provider: groq\n"
        "    model: llama-3.3-70b-versatile\n"
        "    base_url: https://api.groq.com/openai/v1\n"
        "    temperature: 0.0\n"
        "    max_sentences: 3\n"
        "    max_tokens: 128\n"
        "    request_timeout_seconds: 5\n",
        encoding="utf-8",
    )

    rag_config = load_rag_config(config_path)
    generator = build_answer_generator(rag_config.generation)
    assert isinstance(generator, OpenAICompatibleAnswerGenerator)
    assert generator.base_url == "https://api.groq.com/openai/v1"


def test_build_answer_generator_uses_template_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config_path = tmp_path / "rag.yaml"
    config_path.write_text(
        "rag:\n"
        "  retrieval:\n"
        "    dense_top_k: 5\n"
        "    sparse_top_k: 5\n"
        "    hybrid_alpha: 0.5\n"
        "    final_top_k: 3\n"
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

    rag_config = load_rag_config(config_path)
    generator = build_answer_generator(rag_config.generation)
    assert isinstance(generator, TemplateAnswerGenerator)
