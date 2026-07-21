from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

from ingestion.config import CONFIG_DIR
from ingestion.models import Chunk, ParsedDocument

logger = logging.getLogger("ingestion.chunk_store")

CHUNKS_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chunks"
CHUNKING_CONFIG_PATH = CONFIG_DIR / "chunking.yaml"


class ChunkStore:
    """Persist chunk outputs for embedding and audit."""

    def __init__(self, chunks_dir: Path | None = None) -> None:
        self.chunks_dir = chunks_dir or CHUNKS_DATA_DIR
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

    def save(self, document: ParsedDocument, chunks: list[Chunk]) -> Path:
        scheme_dir = self.chunks_dir / document.slug
        scheme_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "document_id": document.document_id,
            "slug": document.slug,
            "scheme_name": document.scheme_name,
            "content_hash": document.content_hash,
            "fetched_at": document.fetched_at.isoformat(),
            "chunk_count": len(chunks),
            "chunks": [self._chunk_to_dict(chunk) for chunk in chunks],
        }

        timestamp = document.fetched_at.astimezone().strftime("%Y-%m-%d_%H-%M-%S")
        history_path = scheme_dir / "history" / f"{timestamp}.json"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path = scheme_dir / "latest.json"

        history_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self._refresh_catalog()
        return latest_path

    def load_latest(self, slug: str) -> list[Chunk]:
        payload = self.load_latest_payload(slug)
        if payload is None:
            return []
        return payload["chunks"]

    def load_latest_payload(self, slug: str) -> dict | None:
        latest_path = self.chunks_dir / slug / "latest.json"
        if not latest_path.exists():
            return None
        with latest_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        return {
            "document_id": payload["document_id"],
            "slug": payload["slug"],
            "scheme_name": payload["scheme_name"],
            "content_hash": payload["content_hash"],
            "fetched_at": payload["fetched_at"],
            "chunk_count": payload.get("chunk_count", 0),
            "chunks": [self._chunk_from_dict(item) for item in payload.get("chunks", [])],
        }

    def _refresh_catalog(self) -> None:
        slugs = sorted(
            path.name
            for path in self.chunks_dir.iterdir()
            if path.is_dir() and (path / "latest.json").exists()
        )
        total_chunks = 0
        for slug in slugs:
            latest = self.chunks_dir / slug / "latest.json"
            with latest.open(encoding="utf-8") as handle:
                total_chunks += json.load(handle).get("chunk_count", 0)

        catalog = {
            "updated_at": datetime.now().astimezone().isoformat(),
            "slugs": slugs,
            "total_chunks": total_chunks,
        }
        (self.chunks_dir / "catalog.json").write_text(
            json.dumps(catalog, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _chunk_to_dict(chunk: Chunk) -> dict:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "token_count": chunk.token_count,
            "metadata": asdict(chunk.metadata),
        }

    @staticmethod
    def _chunk_from_dict(payload: dict) -> Chunk:
        from ingestion.models import ChunkMetadata

        metadata = ChunkMetadata(**payload["metadata"])
        return Chunk(
            chunk_id=payload["chunk_id"],
            document_id=payload["document_id"],
            chunk_index=payload["chunk_index"],
            text=payload["text"],
            token_count=payload["token_count"],
            metadata=metadata,
        )


def load_chunking_config(config_path: Path | None = None) -> dict:
    path = config_path or CHUNKING_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data.get("chunking", {})
