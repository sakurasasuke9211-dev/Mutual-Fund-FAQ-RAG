from __future__ import annotations

import logging
from datetime import datetime

from ingestion.chunk_store import ChunkStore
from ingestion.embedder import EmbeddingService
from ingestion.manifest import load_manifest
from ingestion.models import ScrapeJobSummary
from ingestion.vector_store import VectorStore, VectorStoreError

logger = logging.getLogger("ingestion.embed_phase")


def run_embed_phase(
    scrape_summary: ScrapeJobSummary,
    chunk_store: ChunkStore | None = None,
    embedder: EmbeddingService | None = None,
    vector_store: VectorStore | None = None,
) -> tuple[int, int, int, int]:
    """Embed and upsert chunks for documents whose content changed."""
    chunk_store = chunk_store or ChunkStore()
    embedder = embedder or EmbeddingService()
    vector_store = vector_store or VectorStore()

    changed_slugs = {
        result.slug
        for result in scrape_summary.results
        if result.status == "success" and result.content_changed
    }

    embedded = 0
    embed_failed = 0
    embed_skipped = 0
    vectors_total = 0
    manifest_documents: list[dict[str, str | int]] = []
    existing_manifest = vector_store.load_manifest()
    existing_docs = {
        doc["slug"]: doc for doc in existing_manifest.get("documents", []) if "slug" in doc
    }
    active_slugs = {scheme.slug for scheme in load_manifest().schemes}

    for slug in sorted(existing_docs.keys() | changed_slugs):
        if slug not in active_slugs:
            try:
                vector_store.delete_by_document_id(str(existing_docs[slug]["document_id"]))
                logger.info("Removed vectors for scheme no longer in manifest: %s", slug)
            except (KeyError, VectorStoreError):
                logger.exception("Failed to remove retired scheme vectors: %s", slug)
                manifest_documents.append(existing_docs[slug])
            continue

        if slug not in changed_slugs:
            manifest_documents.append(existing_docs[slug])
            continue

        payload = chunk_store.load_latest_payload(slug)
        if payload is None:
            embed_skipped += 1
            logger.info("Skipping embedding; no chunks found for %s", slug)
            if slug in existing_docs:
                manifest_documents.append(existing_docs[slug])
            continue

        document_id = payload["document_id"]
        chunks = payload["chunks"]
        content_hash = payload["content_hash"]

        try:
            embed_result, vectors_by_id = embedder.embed_chunks(chunks)

            if embed_result.failed_chunk_ids or embed_result.embedded_count == 0:
                embed_failed += 1
                logger.error(
                    "Embedding failures for %s: %s",
                    slug,
                    embed_result.failed_chunk_ids,
                )
                if slug in existing_docs:
                    manifest_documents.append(existing_docs[slug])
                continue

            vector_store.delete_by_document_id(document_id)
            upserted = vector_store.upsert_chunks(chunks, vectors_by_id)
            if upserted == 0:
                embed_failed += 1
                logger.error("No vectors upserted for %s", slug)
                if slug in existing_docs:
                    manifest_documents.append(existing_docs[slug])
                continue

            embedded += 1
            vectors_total += upserted
            manifest_documents.append(
                {
                    "slug": slug,
                    "document_id": document_id,
                    "content_hash": content_hash,
                    "chunk_count": upserted,
                    "last_indexed_at": datetime.now().astimezone().isoformat(),
                }
            )
            logger.info("Indexed %s: %s vectors (%s)", slug, upserted, vector_store.provider)
        except VectorStoreError:
            embed_failed += 1
            logger.exception("Vector store indexing failed for %s", slug)
            if slug in existing_docs:
                manifest_documents.append(existing_docs[slug])
        except Exception:
            embed_failed += 1
            logger.exception("Embedding phase failed for %s", slug)
            if slug in existing_docs:
                manifest_documents.append(existing_docs[slug])

    vector_store.update_manifest(
        embedding_model=embedder.config.model,
        dimensions=embedder.config.dimensions,
        documents=manifest_documents,
    )

    return embedded, embed_failed, embed_skipped, vectors_total
