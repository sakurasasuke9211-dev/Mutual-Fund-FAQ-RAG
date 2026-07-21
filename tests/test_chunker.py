from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ingestion.chunk_store import ChunkStore
from ingestion.chunker import ChunkingService, estimate_tokens
from ingestion.models import FundFacts, ParsedDocument, ParsedSection, SchemeEntry
from ingestion.parser import GrowwHtmlParser

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hdfc_large_cap_sample.html"


@pytest.fixture
def sample_scheme() -> SchemeEntry:
    return SchemeEntry(
        name="HDFC Large Cap Fund – Direct Growth",
        category="large-cap",
        slug="hdfc-large-cap-fund-direct-growth",
        url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    )


@pytest.fixture
def parsed_document(sample_scheme: SchemeEntry) -> ParsedDocument:
    parser = GrowwHtmlParser()
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    return parser.parse_html(
        html=html,
        scheme=sample_scheme,
        amc_name="HDFC Mutual Fund",
        fetched_at=datetime(2026, 7, 17, 9, 15, tzinfo=timezone.utc),
        content_hash="hash123",
    )


@pytest.fixture
def chunker() -> ChunkingService:
    return ChunkingService()


def test_chunker_produces_enriched_chunks(chunker: ChunkingService, parsed_document: ParsedDocument) -> None:
    chunks = chunker.chunk(parsed_document)

    assert len(chunks) >= 3
    assert all(chunk.token_count >= 15 for chunk in chunks)
    assert all("Scheme: HDFC Large Cap Fund" in chunk.text for chunk in chunks)
    assert all(chunk.metadata.source_url.startswith("https://groww.in/") for chunk in chunks)


def test_chunker_groups_fund_details(chunker: ChunkingService, parsed_document: ParsedDocument) -> None:
    chunks = chunker.chunk(parsed_document)
    fund_chunks = [c for c in chunks if c.metadata.section_id == "fund_details"]

    assert len(fund_chunks) == 1
    assert "Expense Ratio" not in fund_chunks[0].text or "Fund Size" in fund_chunks[0].text
    assert "₹1,231.72" in fund_chunks[0].text or any(
        "NAV" in c.text for c in chunks if c.metadata.section_id == "fund_details"
    )


def test_chunker_creates_performance_link_only_chunk(
    chunker: ChunkingService, parsed_document: ParsedDocument
) -> None:
    chunks = chunker.chunk(parsed_document)
    performance = [c for c in chunks if c.metadata.section_id == "performance"]

    assert len(performance) == 1
    assert performance[0].metadata.answer_mode == "link_only"


def test_chunker_deterministic_ids(chunker: ChunkingService, parsed_document: ParsedDocument) -> None:
    first = chunker.chunk(parsed_document)
    second = chunker.chunk(parsed_document)
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_chunker_splits_long_prose(chunker: ChunkingService, parsed_document: ParsedDocument) -> None:
    long_text = " ".join(["This is a long investment objective sentence."] * 80)
    document = ParsedDocument(
        document_id=parsed_document.document_id,
        slug=parsed_document.slug,
        scheme_name=parsed_document.scheme_name,
        scheme_category=parsed_document.scheme_category,
        source_url=parsed_document.source_url,
        amc_name=parsed_document.amc_name,
        fetched_at=parsed_document.fetched_at,
        content_hash=parsed_document.content_hash,
        sections=[
            ParsedSection(
                section_id="overview",
                title="Investment Objective",
                content=long_text,
                fields={"investment_objective": long_text},
            )
        ],
        facts=parsed_document.facts,
    )

    chunks = chunker.chunk(document)
    overview_chunks = [c for c in chunks if c.metadata.section_id == "overview"]
    assert len(overview_chunks) > 1
    assert all(c.token_count <= 550 for c in overview_chunks)


def test_chunk_store_roundtrip(
    parsed_document: ParsedDocument, chunker: ChunkingService, tmp_path: Path
) -> None:
    store = ChunkStore(chunks_dir=tmp_path / "chunks")
    chunks = chunker.chunk(parsed_document)
    store.save(parsed_document, chunks)

    loaded = store.load_latest(parsed_document.slug)
    assert len(loaded) == len(chunks)
    assert loaded[0].chunk_id == chunks[0].chunk_id


def test_estimate_tokens() -> None:
    assert estimate_tokens("one two three four") == 4
