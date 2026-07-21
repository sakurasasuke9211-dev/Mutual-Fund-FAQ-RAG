from __future__ import annotations

import pytest

from citation.models import Citation
from citation.resolver import CitationError, CitationResolver
from retrieval.models import RetrievedChunk


def _chunk(
    *,
    chunk_id: str = "chunk-1",
    source_url: str = "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    scheme_name: str = "HDFC ELSS Tax Saver Fund – Direct Plan Growth",
    last_fetched_at: str = "2026-07-16",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text="Expense Ratio: 1.18%",
        metadata={
            "source_url": source_url,
            "scheme_name": scheme_name,
            "last_fetched_at": last_fetched_at,
            "document_type": "scheme_page",
        },
        dense_score=0.9,
        bm25_score=0.8,
        hybrid_score=0.85,
        rerank_score=1.2,
    )


def test_citation_resolver_uses_top_chunk_metadata() -> None:
    resolver = CitationResolver(
        allowed_source_urls={"https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth"}
    )
    citation = resolver.resolve([_chunk()], "The expense ratio is 1.18%.")

    assert citation.source_url == "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth"
    assert citation.source_title == "HDFC ELSS Tax Saver Fund – Direct Plan Growth"
    assert citation.last_updated == "2026-07-16"


def test_citation_resolver_rejects_disallowed_url() -> None:
    resolver = CitationResolver(allowed_source_urls={"https://groww.in/mutual-funds/allowed"})
    chunk = _chunk(source_url="https://groww.in/mutual-funds/not-allowed")

    with pytest.raises(CitationError, match="allowlist"):
        resolver.resolve([chunk])


def test_citation_resolver_requires_chunks() -> None:
    resolver = CitationResolver(allowed_source_urls=set())

    with pytest.raises(CitationError, match="No retrieved chunks"):
        resolver.resolve([])
