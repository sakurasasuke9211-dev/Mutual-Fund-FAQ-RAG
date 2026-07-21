from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ingestion.models import SchemeEntry, ScrapeResult
from ingestion.parser import GrowwHtmlParser, parse_and_store_facts
from ingestion.facts_store import FundFactsStore

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
def parser(tmp_path: Path) -> GrowwHtmlParser:
    return GrowwHtmlParser(parsed_dir=tmp_path / "parsed")


def test_parse_html_extracts_priority_fields(
    parser: GrowwHtmlParser, sample_scheme: SchemeEntry
) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    document = parser.parse_html(
        html=html,
        scheme=sample_scheme,
        amc_name="HDFC Mutual Fund",
        fetched_at=datetime(2026, 7, 17, 9, 15, tzinfo=timezone.utc),
        content_hash="hash123",
    )

    assert document.facts.nav == "₹1,231.72"
    assert document.facts.expense_ratio == "1.03%"
    assert document.facts.minimum_sip == "₹100"
    assert document.facts.fund_size == "₹39,023.69 Cr"
    assert document.facts.rating == "4"
    assert any(section.section_id == "fund_details" for section in document.sections)


def test_parse_scrape_result_and_store_facts(
    parser: GrowwHtmlParser, sample_scheme: SchemeEntry, tmp_path: Path
) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    raw_path = tmp_path / "sample.html"
    raw_path.write_text(html, encoding="utf-8")

    scrape_result = ScrapeResult(
        url=sample_scheme.url,
        slug=sample_scheme.slug,
        scheme_name=sample_scheme.name,
        status="success",
        http_status=200,
        fetched_at=datetime(2026, 7, 17, 9, 15, tzinfo=timezone.utc),
        content_hash="hash123",
        raw_path=str(raw_path),
        normalized_path=str(tmp_path / "sample.normalized.txt"),
        content_changed=True,
    )

    facts_store = FundFactsStore(facts_dir=tmp_path / "facts")
    parse_result = parse_and_store_facts(
        scheme=sample_scheme,
        scrape_result=scrape_result,
        amc_name="HDFC Mutual Fund",
        facts_store=facts_store,
        parser=parser,
    )

    assert parse_result.status == "success"
    loaded = facts_store.load_latest(sample_scheme.slug)
    assert loaded is not None
    assert loaded.expense_ratio == "1.03%"


def test_parse_live_groww_html_if_available(sample_scheme: SchemeEntry, tmp_path: Path) -> None:
    live_html = Path("data/raw/_debug.html")
    if not live_html.exists():
        pytest.skip("Live Groww HTML snapshot not available")

    parser = GrowwHtmlParser(parsed_dir=tmp_path / "parsed")
    document = parser.parse_file(
        html_path=live_html,
        scheme=sample_scheme,
        amc_name="HDFC Mutual Fund",
        fetched_at=datetime(2026, 7, 17, 9, 15, tzinfo=timezone.utc),
        content_hash="live",
    )

    assert document.facts.expense_ratio is not None
    assert document.facts.minimum_sip is not None
