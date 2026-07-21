from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ingestion.models import SchemeEntry
from ingestion.scraper import GrowwScrapingService
from ingestion.config import ScraperSettings


@pytest.fixture
def sample_scheme() -> SchemeEntry:
    return SchemeEntry(
        name="HDFC Large Cap Fund – Direct Growth",
        category="large-cap",
        slug="hdfc-large-cap-fund-direct-growth",
        url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    )


@pytest.fixture
def scraper(tmp_path: Path) -> GrowwScrapingService:
    settings = ScraperSettings(
        raw_data_dir=tmp_path / "raw",
        use_playwright_fallback=False,
        rate_limit_seconds=0,
    )
    return GrowwScrapingService(settings=settings)


SAMPLE_HTML = """
<html>
  <head><title>HDFC Large Cap Fund</title></head>
  <body>
    <script>console.log("ignore")</script>
    <h1>HDFC Large Cap Fund – Direct Growth</h1>
    <div>Expense Ratio: 1.01%</div>
    <div>Exit Load: 1% if redeemed within 1 year</div>
    <div>Minimum SIP: ₹100</div>
    <div>Benchmark: NIFTY 100 Total Return Index</div>
    <div>Riskometer: Very High</div>
  </body>
</html>
"""


def test_normalize_html_strips_scripts(scraper: GrowwScrapingService) -> None:
    normalized = scraper.normalize_html(SAMPLE_HTML)
    assert "console.log" not in normalized
    assert "Expense Ratio: 1.01%" in normalized


def test_compute_hash_is_deterministic(scraper: GrowwScrapingService) -> None:
    normalized = scraper.normalize_html(SAMPLE_HTML)
    assert scraper.compute_hash(normalized) == scraper.compute_hash(normalized)


def test_scrape_url_success(scraper: GrowwScrapingService, sample_scheme: SchemeEntry, mocker) -> None:
    mocker.patch.object(
        scraper,
        "_fetch_with_retries",
        return_value=(SAMPLE_HTML, 200, False),
    )

    result = scraper.scrape_url(sample_scheme)

    assert result.status == "success"
    assert result.http_status == 200
    assert result.content_hash is not None
    assert result.raw_path is not None
    assert result.normalized_path is not None
    assert result.content_changed is True
    assert Path(result.raw_path).exists()


def test_scrape_url_unchanged_on_second_run(
    scraper: GrowwScrapingService, sample_scheme: SchemeEntry, mocker
) -> None:
    mocker.patch.object(
        scraper,
        "_fetch_with_retries",
        return_value=(SAMPLE_HTML, 200, False),
    )

    first = scraper.scrape_url(sample_scheme)
    second = scraper.scrape_url(sample_scheme)

    assert first.status == "success"
    assert second.status == "success"
    assert second.content_changed is False


def test_scrape_url_failure(scraper: GrowwScrapingService, sample_scheme: SchemeEntry, mocker) -> None:
    mocker.patch.object(
        scraper,
        "_fetch_with_retries",
        side_effect=RuntimeError("network down"),
    )

    result = scraper.scrape_url(sample_scheme)

    assert result.status == "failed"
    assert result.error is not None
    assert result.raw_path is None
