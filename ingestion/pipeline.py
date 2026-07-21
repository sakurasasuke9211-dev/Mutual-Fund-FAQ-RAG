from __future__ import annotations

import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from ingestion.chunk_phase import run_chunk_phase
from ingestion.embed_phase import run_embed_phase
from ingestion.logging_config import setup_ingestion_logging, utc_now, write_job_summary
from ingestion.config import LOGS_DIR, load_env_file
from ingestion.manifest import get_scheme_by_slug, load_manifest
from ingestion.models import IngestionJobSummary, ParseResult, ScrapeJobSummary
from ingestion.parser import parse_and_store_facts
from ingestion.retention import prune_generated_artifacts
from ingestion.scraper import GrowwScrapingService

logger = logging.getLogger("ingestion.pipeline")


class IngestionPipelineError(Exception):
    """Raised when the ingestion pipeline cannot complete scraping."""


def run_scrape_phase() -> ScrapeJobSummary:
    """Scrape all Groww scheme pages from the manifest."""
    started_at = utc_now()
    manifest = load_manifest()
    scraper = GrowwScrapingService()
    results = scraper.scrape_all(manifest.schemes)
    finished_at = utc_now()

    succeeded = sum(1 for result in results if result.status == "success")
    failed = sum(1 for result in results if result.status == "failed")
    changed = sum(
        1 for result in results if result.status == "success" and result.content_changed
    )
    skipped_unchanged = sum(
        1
        for result in results
        if result.status == "success" and not result.content_changed
    )

    summary = ScrapeJobSummary(
        started_at=started_at,
        finished_at=finished_at,
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        changed=changed,
        skipped_unchanged=skipped_unchanged,
        results=results,
    )

    if summary.all_failed:
        raise IngestionPipelineError(
            "All scrape targets failed. Existing index and snapshots are unchanged."
        )

    return summary


def run_parse_phase(scrape_summary: ScrapeJobSummary) -> tuple[int, int, int, list[ParseResult]]:
    """Parse successful scrapes and persist structured fund facts."""
    manifest = load_manifest()
    parsed = 0
    parse_failed = 0
    facts_saved = 0
    parse_results: list[ParseResult] = []

    for scrape_result in scrape_summary.results:
        if scrape_result.status != "success":
            continue

        scheme = get_scheme_by_slug(manifest, scrape_result.slug)
        if scheme is None:
            logger.error("No manifest entry for slug %s", scrape_result.slug)
            parse_failed += 1
            continue

        parse_result = parse_and_store_facts(
            scheme=scheme,
            scrape_result=scrape_result,
            amc_name=manifest.amc,
        )
        parse_results.append(parse_result)

        if parse_result.status == "success":
            parsed += 1
            facts_saved += 1
            logger.info(
                "Parsed %s: facts=%s",
                scheme.slug,
                parse_result.document.facts.as_dict() if parse_result.document else {},
            )
        else:
            parse_failed += 1
            logger.error("Parse failed for %s: %s", scheme.slug, parse_result.error)

    return parsed, parse_failed, facts_saved, parse_results


def _log_scrape_summary(summary: ScrapeJobSummary) -> None:
    logger.info(
        "Scrape job complete: total=%s succeeded=%s failed=%s changed=%s unchanged=%s",
        summary.total,
        summary.succeeded,
        summary.failed,
        summary.changed,
        summary.skipped_unchanged,
    )
    for result in summary.results:
        if result.status == "success":
            logger.info(
                "  [OK] %s hash=%s changed=%s path=%s",
                result.slug,
                (result.content_hash or "")[:12],
                result.content_changed,
                result.raw_path,
            )
        else:
            logger.error("  [FAIL] %s error=%s", result.slug, result.error)


def _persist_job_summary(job_summary: IngestionJobSummary) -> Path:
    timestamp = job_summary.finished_at.astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    summary_path = LOGS_DIR / f"ingestion_summary_{timestamp}.json"
    payload = {
        "started_at": job_summary.started_at.isoformat(),
        "finished_at": job_summary.finished_at.isoformat(),
        "scrape": asdict(job_summary.scrape),
        "parsed": job_summary.parsed,
        "parse_failed": job_summary.parse_failed,
        "facts_saved": job_summary.facts_saved,
        "chunked": job_summary.chunked,
        "chunk_failed": job_summary.chunk_failed,
        "chunks_total": job_summary.chunks_total,
        "chunks_skipped": job_summary.chunks_skipped,
        "embedded": job_summary.embedded,
        "embed_failed": job_summary.embed_failed,
        "embed_skipped": job_summary.embed_skipped,
        "vectors_total": job_summary.vectors_total,
    }
    write_job_summary(summary_path, payload)
    write_job_summary(LOGS_DIR / "ingestion_summary_latest.json", payload)
    return summary_path


def run_ingestion_pipeline() -> IngestionJobSummary:
    """Run the full daily ingestion flow in order.

    1. Scrape latest Groww scheme pages
    2. Parse HTML and store fund facts
    3. Chunk changed documents
    4. Embed chunks and upsert vectors to Chroma Cloud
    """
    started_at = utc_now()
    logger.info(
        "Ingestion pipeline starting: scrape → parse → chunk → embed → Chroma Cloud index"
    )

    scrape_summary = run_scrape_phase()
    logger.info("Phase 1/4 complete: scrape")

    parsed, parse_failed, facts_saved, parse_results = run_parse_phase(scrape_summary)
    logger.info("Phase 2/4 complete: parse")

    chunked, chunk_failed, chunks_total, chunks_skipped = run_chunk_phase(
        parse_results, scrape_summary
    )
    logger.info("Phase 3/4 complete: chunk")

    embedded, embed_failed, embed_skipped, vectors_total = run_embed_phase(scrape_summary)
    logger.info("Phase 4/4 complete: embed + Chroma Cloud index")

    finished_at = utc_now()
    return IngestionJobSummary(
        started_at=started_at,
        finished_at=finished_at,
        scrape=scrape_summary,
        parsed=parsed,
        parse_failed=parse_failed,
        facts_saved=facts_saved,
        chunked=chunked,
        chunk_failed=chunk_failed,
        chunks_total=chunks_total,
        chunks_skipped=chunks_skipped,
        embedded=embedded,
        embed_failed=embed_failed,
        embed_skipped=embed_skipped,
        vectors_total=vectors_total,
    )


def main() -> None:
    load_env_file()
    activity_log = setup_ingestion_logging()
    logger.info("Scheduler activity log: %s", activity_log)
    logger.info(
        "Scheduler trigger: source=%s python=%s vector_store=%s",
        os.getenv("GITHUB_EVENT_NAME", "local_manual"),
        sys.version.split()[0],
        os.getenv("VECTOR_STORE_PROVIDER", "config_default"),
    )

    try:
        job_summary = run_ingestion_pipeline()
    except IngestionPipelineError:
        logger.exception("Ingestion pipeline failed during scrape phase")
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected ingestion pipeline failure")
        sys.exit(1)

    _log_scrape_summary(job_summary.scrape)
    logger.info(
        "Parse phase complete: parsed=%s failed=%s facts_saved=%s",
        job_summary.parsed,
        job_summary.parse_failed,
        job_summary.facts_saved,
    )
    logger.info(
        "Chunk phase complete: chunked=%s failed=%s total_chunks=%s skipped=%s",
        job_summary.chunked,
        job_summary.chunk_failed,
        job_summary.chunks_total,
        job_summary.chunks_skipped,
    )
    logger.info(
        "Embed/index phase complete: embedded=%s failed=%s skipped=%s vectors_total=%s",
        job_summary.embedded,
        job_summary.embed_failed,
        job_summary.embed_skipped,
        job_summary.vectors_total,
    )
    summary_path = _persist_job_summary(job_summary)
    if os.getenv("INGESTION_KEEP_LATEST_ONLY", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }:
        retention = prune_generated_artifacts(
            current_activity_log=activity_log,
            current_summary=summary_path,
        )
        logger.info(
            "Retention complete: files_removed=%s directories_removed=%s",
            retention.files_removed,
            retention.directories_removed,
        )
    logger.info("Ingestion pipeline finished successfully; activity_log=%s", activity_log)


if __name__ == "__main__":
    main()
