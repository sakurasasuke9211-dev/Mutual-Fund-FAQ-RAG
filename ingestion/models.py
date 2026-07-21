from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class SchemeEntry:
    name: str
    category: str
    slug: str
    url: str


@dataclass(frozen=True)
class RefusalLink:
    label: str
    url: str


@dataclass(frozen=True)
class CorpusManifest:
    amc: str
    source_platform: str
    format: str
    schemes: list[SchemeEntry]
    refusal_links: list[RefusalLink] = field(default_factory=list)


@dataclass(frozen=True)
class ScrapeResult:
    url: str
    slug: str
    scheme_name: str
    status: Literal["success", "failed"]
    http_status: int | None
    fetched_at: datetime
    content_hash: str | None
    raw_path: str | None
    normalized_path: str | None
    content_changed: bool
    error: str | None = None


@dataclass(frozen=True)
class FundFacts:
    """Structured priority metrics extracted from a Groww scheme page."""

    slug: str
    scheme_name: str
    scheme_category: str
    source_url: str
    nav: str | None
    expense_ratio: str | None
    minimum_sip: str | None
    fund_size: str | None
    rating: str | None
    fetched_at: datetime
    content_hash: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "nav": self.nav,
            "expense_ratio": self.expense_ratio,
            "minimum_sip": self.minimum_sip,
            "fund_size": self.fund_size,
            "rating": self.rating,
        }

    def missing_fields(self) -> list[str]:
        return [key for key, value in self.as_dict().items() if not value]


@dataclass(frozen=True)
class ParsedSection:
    section_id: str
    title: str
    content: str
    fields: dict[str, str]


@dataclass(frozen=True)
class ParsedDocument:
    document_id: str
    slug: str
    scheme_name: str
    scheme_category: str
    source_url: str
    amc_name: str
    fetched_at: datetime
    content_hash: str
    sections: list[ParsedSection]
    facts: FundFacts


@dataclass(frozen=True)
class ParseResult:
    slug: str
    status: Literal["success", "failed"]
    document: ParsedDocument | None = None
    error: str | None = None


@dataclass(frozen=True)
class ChunkMetadata:
    source_url: str
    source_domain: str
    document_type: str
    amc_name: str
    scheme_name: str
    scheme_category: str
    section_id: str
    section_title: str
    answer_mode: str
    last_fetched_at: str
    content_hash: str
    language: str
    token_count: int


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    token_count: int
    metadata: ChunkMetadata


@dataclass(frozen=True)
class ChunkResult:
    slug: str
    status: Literal["success", "failed", "skipped"]
    chunks: list[Chunk] = field(default_factory=list)
    document_id: str | None = None
    content_hash: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class EmbedResult:
    embedded_count: int
    skipped_count: int
    failed_chunk_ids: list[str]
    model: str
    dimensions: int


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    dimensions: int
    batch_size: int
    normalize: bool
    max_retries: int
    retry_delay_seconds: int
    query_prefix: str = ""


@dataclass(frozen=True)
class VectorStoreConfig:
    provider: str
    collection_name: str
    cloud_host: str
    cloud_port: int


@dataclass(frozen=True)
class ScrapeJobSummary:
    started_at: datetime
    finished_at: datetime
    total: int
    succeeded: int
    failed: int
    changed: int
    skipped_unchanged: int
    results: list[ScrapeResult]

    @property
    def all_failed(self) -> bool:
        return self.total > 0 and self.succeeded == 0


@dataclass(frozen=True)
class IngestionJobSummary:
    started_at: datetime
    finished_at: datetime
    scrape: ScrapeJobSummary
    parsed: int
    parse_failed: int
    facts_saved: int
    chunked: int
    chunk_failed: int
    chunks_total: int
    chunks_skipped: int
    embedded: int
    embed_failed: int
    embed_skipped: int
    vectors_total: int
