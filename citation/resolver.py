from __future__ import annotations

import logging
import re

from citation.models import Citation
from ingestion.manifest import allowed_urls, load_manifest
from retrieval.models import RetrievedChunk

logger = logging.getLogger("citation.resolver")


class CitationError(Exception):
    """Raised when a citation cannot be resolved safely."""


class CitationResolver:
    """Resolve exactly one allowlisted Groww URL from retrieved chunks."""

    def __init__(self, allowed_source_urls: set[str] | None = None) -> None:
        self.allowed_source_urls = allowed_source_urls or allowed_urls(load_manifest())

    def resolve(self, chunks: list[RetrievedChunk], generated_text: str = "") -> Citation:
        if not chunks:
            raise CitationError("No retrieved chunks available for citation")

        primary = chunks[0]
        source_url = str(primary.metadata.get("source_url", "")).strip()
        if not source_url:
            raise CitationError("Top retrieved chunk is missing source_url metadata")
        if source_url not in self.allowed_source_urls:
            raise CitationError(f"Source URL is not in corpus allowlist: {source_url}")

        mentioned_urls = self._extract_urls(generated_text)
        if mentioned_urls:
            disallowed = [url for url in mentioned_urls if url not in self.allowed_source_urls]
            if disallowed:
                logger.warning(
                    "Generator mentioned disallowed URLs %s; overriding with chunk metadata",
                    disallowed,
                )
            elif len(mentioned_urls) > 1:
                logger.warning(
                    "Generator mentioned multiple URLs; overriding with top chunk metadata"
                )

        return Citation(
            source_url=source_url,
            source_title=str(primary.metadata.get("scheme_name", "")).strip(),
            last_updated=str(primary.metadata.get("last_fetched_at", "")).strip(),
        )

    @staticmethod
    def _extract_urls(text: str) -> list[str]:
        if not text:
            return []
        return re.findall(r"https?://[^\s)>\"]+", text)
