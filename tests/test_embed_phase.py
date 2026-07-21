from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ingestion.chunk_store import ChunkStore
from ingestion.embed_phase import run_embed_phase
from ingestion.embedder import DeterministicEmbeddingProvider, EmbeddingConfig, EmbeddingService
from ingestion.models import Chunk, ChunkMetadata, ScrapeResult, ScrapeJobSummary, VectorStoreConfig
from ingestion.vector_store import VectorStore


def _make_chunk(chunk_id: str, document_id: str) -> Chunk:
    metadata = ChunkMetadata(
        source_url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        source_domain="groww.in",
        document_type="scheme_page",
        amc_name="HDFC Mutual Fund",
        scheme_name="HDFC Large Cap Fund – Direct Growth",
        scheme_category="large-cap",
        section_id="fund_details",
        section_title="Fund Details",
        answer_mode="factual",
        last_fetched_at="2026-07-17",
        content_hash="hash123",
        language="en",
        token_count=40,
    )
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        chunk_index=0,
        text="Scheme: HDFC Large Cap Fund – Direct Growth\nNAV: ₹1,231.72",
        token_count=40,
        metadata=metadata,
    )


def test_run_embed_phase(tmp_path) -> None:
    slug = "hdfc-large-cap-fund-direct-growth"
    document_id = "doc-1"
    chunk = _make_chunk("chunk-1", document_id)

    chunk_store = ChunkStore(chunks_dir=tmp_path / "chunks")
    chunk_store.save(
        document=type(
            "Doc",
            (),
            {
                "document_id": document_id,
                "slug": slug,
                "scheme_name": "HDFC Large Cap Fund – Direct Growth",
                "content_hash": "hash123",
                "fetched_at": datetime.now(timezone.utc),
            },
        )(),
        chunks=[chunk],
    )

    config = EmbeddingConfig(
        provider="local",
        model="deterministic-local",
        dimensions=16,
        batch_size=8,
        normalize=True,
        max_retries=1,
        retry_delay_seconds=0,
    )
    embedder = EmbeddingService(
        config=config,
        provider=DeterministicEmbeddingProvider(dimensions=16),
    )
    vector_store = VectorStore(
        index_dir=tmp_path / "index",
        config=VectorStoreConfig(
            provider="chroma_local",
            collection_name="test_mutual_fund_faq_chunks",
            cloud_host="api.trychroma.com",
            cloud_port=443,
        ),
    )

    now = datetime.now(timezone.utc)
    scrape_summary = ScrapeJobSummary(
        started_at=now,
        finished_at=now,
        total=1,
        succeeded=1,
        failed=0,
        changed=1,
        skipped_unchanged=0,
        results=[
            ScrapeResult(
                url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
                slug=slug,
                scheme_name="HDFC Large Cap Fund – Direct Growth",
                status="success",
                http_status=200,
                fetched_at=now,
                content_hash="hash123",
                raw_path="/tmp/a.html",
                normalized_path="/tmp/a.normalized.txt",
                content_changed=True,
            )
        ],
    )

    embedded, embed_failed, embed_skipped, vectors_total = run_embed_phase(
        scrape_summary,
        chunk_store=chunk_store,
        embedder=embedder,
        vector_store=vector_store,
    )

    assert embedded == 1
    assert embed_failed == 0
    assert vectors_total == 1
    assert vector_store.count() == 1
    manifest = vector_store.load_manifest()
    assert manifest["total_chunks"] == 1


def test_run_embed_phase_removes_vectors_for_retired_scheme(mocker) -> None:
    now = datetime.now(timezone.utc)
    scrape_summary = ScrapeJobSummary(
        started_at=now,
        finished_at=now,
        total=0,
        succeeded=0,
        failed=0,
        changed=0,
        skipped_unchanged=0,
        results=[],
    )
    vector_store = mocker.Mock()
    vector_store.load_manifest.return_value = {
        "documents": [
            {
                "slug": "retired-scheme",
                "document_id": "retired-document",
                "content_hash": "old",
                "chunk_count": 1,
            }
        ]
    }
    vector_store.provider = "chroma_local"
    embedder = mocker.Mock()
    embedder.config.model = "test-model"
    embedder.config.dimensions = 16
    mocker.patch("ingestion.embed_phase.load_manifest", return_value=mocker.Mock(schemes=[]))

    run_embed_phase(
        scrape_summary,
        chunk_store=mocker.Mock(),
        embedder=embedder,
        vector_store=vector_store,
    )

    vector_store.delete_by_document_id.assert_called_once_with("retired-document")
    assert vector_store.update_manifest.call_args.kwargs["documents"] == []
