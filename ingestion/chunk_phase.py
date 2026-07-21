from __future__ import annotations

import logging

from ingestion.chunk_store import ChunkStore
from ingestion.chunker import ChunkingService
from ingestion.models import ChunkResult, ParseResult, ScrapeJobSummary

logger = logging.getLogger("ingestion.pipeline")


def run_chunk_phase(
    parse_results: list[ParseResult],
    scrape_summary: ScrapeJobSummary,
    chunker: ChunkingService | None = None,
    chunk_store: ChunkStore | None = None,
) -> tuple[int, int, int, int]:
    """Chunk parsed documents when source content changed."""
    chunker = chunker or ChunkingService()
    chunk_store = chunk_store or ChunkStore()

    changed_slugs = {
        result.slug
        for result in scrape_summary.results
        if result.status == "success" and result.content_changed
    }

    chunked = 0
    chunk_failed = 0
    chunks_total = 0
    chunks_skipped = 0

    for parse_result in parse_results:
        if parse_result.status != "success" or parse_result.document is None:
            continue

        document = parse_result.document
        if document.slug not in changed_slugs:
            chunks_skipped += 1
            logger.info("Skipping chunking for unchanged document: %s", document.slug)
            continue

        chunk_result = _chunk_and_store(document, chunker, chunk_store)
        if chunk_result.status == "success":
            chunked += 1
            chunks_total += len(chunk_result.chunks)
            logger.info(
                "Chunked %s: %s chunks",
                document.slug,
                len(chunk_result.chunks),
            )
        else:
            chunk_failed += 1
            logger.error("Chunk failed for %s: %s", document.slug, chunk_result.error)

    return chunked, chunk_failed, chunks_total, chunks_skipped


def _chunk_and_store(
    document,
    chunker: ChunkingService,
    chunk_store: ChunkStore,
) -> ChunkResult:
    result = chunker.chunk_document(document)
    if result.status == "success":
        chunk_store.save(document, result.chunks)
        return ChunkResult(
            slug=result.slug,
            status="success",
            chunks=result.chunks,
            document_id=document.document_id,
            content_hash=document.content_hash,
        )
    return result
