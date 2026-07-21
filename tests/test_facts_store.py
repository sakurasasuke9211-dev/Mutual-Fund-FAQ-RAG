from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ingestion.facts_store import FundFactsStore
from ingestion.models import FundFacts


@pytest.fixture
def sample_facts() -> FundFacts:
    return FundFacts(
        slug="hdfc-large-cap-fund-direct-growth",
        scheme_name="HDFC Large Cap Fund – Direct Growth",
        scheme_category="large-cap",
        source_url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        nav="₹1,025.43",
        expense_ratio="1.01%",
        minimum_sip="₹100",
        fund_size="₹30,842 Cr",
        rating="5",
        fetched_at=datetime(2026, 7, 17, 9, 15, tzinfo=timezone.utc),
        content_hash="abc123",
    )


def test_save_and_load_latest(tmp_path, sample_facts: FundFacts) -> None:
    store = FundFactsStore(facts_dir=tmp_path)
    store.save(sample_facts)

    loaded = store.load_latest(sample_facts.slug)
    assert loaded is not None
    assert loaded.nav == "₹1,025.43"
    assert loaded.expense_ratio == "1.01%"
    assert loaded.minimum_sip == "₹100"
    assert loaded.fund_size == "₹30,842 Cr"
    assert loaded.rating == "5"


def test_get_fact(tmp_path, sample_facts: FundFacts) -> None:
    store = FundFactsStore(facts_dir=tmp_path)
    store.save(sample_facts)

    assert store.get_fact(sample_facts.slug, "expense_ratio") == "1.01%"
    assert store.get_fact(sample_facts.slug, "nav") == "₹1,025.43"


def test_load_all_latest(tmp_path, sample_facts: FundFacts) -> None:
    store = FundFactsStore(facts_dir=tmp_path)
    store.save(sample_facts)

    all_facts = store.load_all_latest()
    assert len(all_facts) == 1
    assert all_facts[0].slug == sample_facts.slug


def test_facts_to_chunk_text(sample_facts: FundFacts) -> None:
    text = FundFactsStore.facts_to_chunk_text(sample_facts)
    assert "Expense Ratio: 1.01%" in text
    assert "Minimum SIP: ₹100" in text
    assert "Fund Size: ₹30,842 Cr" in text
