from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.models import ScrapeResult
from ingestion.pipeline import IngestionPipelineError, run_ingestion_pipeline, run_parse_phase, run_scrape_phase
from ingestion.logging_config import utc_now


def test_run_scrape_phase_success(mocker) -> None:
    now = utc_now()
    mock_results = [
        ScrapeResult(
            url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            slug="hdfc-large-cap-fund-direct-growth",
            scheme_name="HDFC Large Cap Fund – Direct Growth",
            status="success",
            http_status=200,
            fetched_at=now,
            content_hash="abc",
            raw_path="/tmp/a.html",
            normalized_path="/tmp/a.normalized.txt",
            content_changed=True,
        )
    ]
    mocker.patch("ingestion.pipeline.load_manifest")
    mocker.patch(
        "ingestion.pipeline.GrowwScrapingService.scrape_all",
        return_value=mock_results,
    )

    summary = run_scrape_phase()
    assert summary.succeeded == 1
    assert summary.failed == 0


def test_run_scrape_phase_all_failed(mocker) -> None:
    now = utc_now()
    mock_results = [
        ScrapeResult(
            url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            slug="hdfc-large-cap-fund-direct-growth",
            scheme_name="HDFC Large Cap Fund – Direct Growth",
            status="failed",
            http_status=None,
            fetched_at=now,
            content_hash=None,
            raw_path=None,
            normalized_path=None,
            content_changed=False,
            error="timeout",
        )
    ]
    mocker.patch("ingestion.pipeline.load_manifest")
    mocker.patch(
        "ingestion.pipeline.GrowwScrapingService.scrape_all",
        return_value=mock_results,
    )

    with pytest.raises(IngestionPipelineError):
        run_scrape_phase()


def test_run_parse_phase(mocker, tmp_path) -> None:
    now = utc_now()
    html_path = tmp_path / "sample.html"
    html_path.write_text(
        Path("tests/fixtures/hdfc_large_cap_sample.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    scrape_results = [
        ScrapeResult(
            url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            slug="hdfc-large-cap-fund-direct-growth",
            scheme_name="HDFC Large Cap Fund – Direct Growth",
            status="success",
            http_status=200,
            fetched_at=now,
            content_hash="abc",
            raw_path=str(html_path),
            normalized_path=str(tmp_path / "sample.normalized.txt"),
            content_changed=True,
        )
    ]
    scrape_summary = mocker.Mock(
        results=scrape_results,
        succeeded=1,
        failed=0,
    )

    mocker.patch("ingestion.pipeline.load_manifest")
    mocker.patch(
        "ingestion.pipeline.get_scheme_by_slug",
        return_value=mocker.Mock(
            slug="hdfc-large-cap-fund-direct-growth",
            name="HDFC Large Cap Fund – Direct Growth",
            category="large-cap",
            url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        ),
    )
    mocker.patch("ingestion.pipeline.parse_and_store_facts", side_effect=[
        mocker.Mock(status="success", document=mocker.Mock())
    ] * 1)

    parsed, parse_failed, facts_saved, parse_results = run_parse_phase(scrape_summary)
    assert parsed == 1
    assert parse_failed == 0
    assert facts_saved == 1
    assert len(parse_results) == 1


def test_run_chunk_phase(mocker, tmp_path) -> None:
    from ingestion.chunk_phase import run_chunk_phase
    from ingestion.models import ParseResult

    now = utc_now()
    document = mocker.Mock(slug="hdfc-large-cap-fund-direct-growth", content_hash="abc")
    parse_results = [ParseResult(slug="hdfc-large-cap-fund-direct-growth", status="success", document=document)]
    scrape_summary = mocker.Mock(
        results=[
            ScrapeResult(
                url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
                slug="hdfc-large-cap-fund-direct-growth",
                scheme_name="HDFC Large Cap Fund – Direct Growth",
                status="success",
                http_status=200,
                fetched_at=now,
                content_hash="abc",
                raw_path="/tmp/a.html",
                normalized_path="/tmp/a.normalized.txt",
                content_changed=True,
            )
        ]
    )

    mocker.patch(
        "ingestion.chunk_phase._chunk_and_store",
        return_value=mocker.Mock(status="success", chunks=[mocker.Mock(), mocker.Mock()]),
    )

    chunked, chunk_failed, chunks_total, chunks_skipped = run_chunk_phase(
        parse_results, scrape_summary
    )
    assert chunked == 1
    assert chunk_failed == 0
    assert chunks_total == 2
    assert chunks_skipped == 0


def test_run_ingestion_pipeline_calls_phases_in_order(mocker) -> None:
    call_order: list[str] = []

    mocker.patch(
        "ingestion.pipeline.run_scrape_phase",
        side_effect=lambda: call_order.append("scrape") or mocker.Mock(
            results=[], total=0, succeeded=0, failed=0, changed=0, skipped_unchanged=0
        ),
    )
    mocker.patch(
        "ingestion.pipeline.run_parse_phase",
        side_effect=lambda _summary: call_order.append("parse") or (0, 0, 0, []),
    )
    mocker.patch(
        "ingestion.pipeline.run_chunk_phase",
        side_effect=lambda *_args: call_order.append("chunk") or (0, 0, 0, 0),
    )
    mocker.patch(
        "ingestion.pipeline.run_embed_phase",
        side_effect=lambda _summary: call_order.append("embed") or (0, 0, 0, 0),
    )
    mocker.patch("ingestion.pipeline.load_env_file")
    mocker.patch("ingestion.pipeline.setup_ingestion_logging")
    mocker.patch("ingestion.pipeline._persist_job_summary")
    mocker.patch("ingestion.pipeline.prune_generated_artifacts")

    run_ingestion_pipeline()
    assert call_order == ["scrape", "parse", "chunk", "embed"]
