from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ingestion.chunk_store import load_chunking_config
from ingestion.manifest import allowed_urls, load_manifest
from ingestion.models import Chunk, ChunkMetadata, ChunkResult, ParsedDocument, ParsedSection

logger = logging.getLogger("ingestion.chunker")

NAMESPACE_URL = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

FIELD_LABELS = {
    "nav": "NAV",
    "expense_ratio": "Expense Ratio",
    "minimum_sip": "Minimum SIP",
    "minimum_lumpsum": "Minimum Lumpsum",
    "additional_purchase": "Additional Purchase",
    "fund_size": "Fund Size",
    "rating": "Rating",
    "exit_load": "Exit Load",
    "stamp_duty": "Stamp Duty",
    "benchmark": "Benchmark",
    "riskometer": "Riskometer",
    "risk_level": "Risk Level",
    "lock_in_period": "Lock-in Period",
    "tax_benefit": "Tax Benefit",
    "investment_objective": "Investment Objective",
}

ATTRIBUTE_GROUPS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "fees_and_loads": ("fees_and_loads", "Fees & Loads", ("expense_ratio", "exit_load", "stamp_duty")),
    "investment_limits": (
        "investment_limits",
        "Investment Limits",
        ("minimum_sip", "minimum_lumpsum", "additional_purchase"),
    ),
    "benchmark_and_risk": (
        "benchmark_and_risk",
        "Benchmark & Risk",
        ("benchmark", "riskometer", "risk_level"),
    ),
    "lock_in_and_tax": (
        "lock_in_and_tax",
        "Lock-in & Tax",
        ("lock_in_period", "tax_benefit"),
    ),
    "fund_details": (
        "fund_details",
        "Fund Details",
        ("nav", "fund_size", "rating"),
    ),
}

PROSE_SECTIONS = {"overview", "holdings"}
LINK_ONLY_SECTIONS = {"performance"}
PRIORITY_FIELD_LABELS = {
    "NAV",
    "Expense Ratio",
    "Minimum SIP",
    "Fund Size",
    "Rating",
}
HEADER_TOKEN_OVERHEAD = 25


@dataclass(frozen=True)
class ChunkingSettings:
    min_tokens: int = 30
    max_tokens: int = 500
    overlap_tokens: int = 50
    prose_target_tokens: int = 300
    enrichment_template: str = (
        "Scheme: {scheme_name}\n"
        "Category: {scheme_category}\n"
        "Section: {section_title}\n"
        "Source: {source_url}\n\n"
        "{chunk_body}"
    )


class ChunkingService:
    """Split parsed Groww documents into enriched retrieval-ready chunks."""

    def __init__(self, settings: ChunkingSettings | None = None) -> None:
        if settings is None:
            config = load_chunking_config()
            settings = ChunkingSettings(
                min_tokens=int(config.get("min_tokens", 30)),
                max_tokens=int(config.get("max_tokens", 500)),
                overlap_tokens=int(config.get("overlap_tokens", 50)),
                prose_target_tokens=int(config.get("prose_target_tokens", 300)),
                enrichment_template=config.get(
                    "enrichment_template", ChunkingSettings.enrichment_template
                ).strip(),
            )
        self.settings = settings
        self._allowlist = allowed_urls(load_manifest())

    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        all_fields = self._collect_fields(document)
        chunk_bodies = self._build_chunk_bodies(document, all_fields)

        chunks: list[Chunk] = []
        chunk_index = 0

        for section_id, section_title, body, answer_mode in chunk_bodies:
            for split_body in self._split_oversized_prose(body):
                enriched = self._enrich(
                    document=document,
                    section_title=section_title,
                    chunk_body=split_body,
                )
                token_count = estimate_tokens(enriched)
                if not self._should_keep_chunk(enriched, token_count):
                    logger.debug(
                        "Discarding chunk for %s/%s (%s tokens)",
                        document.slug,
                        section_id,
                        token_count,
                    )
                    continue

                metadata = ChunkMetadata(
                    source_url=document.source_url,
                    source_domain=urlparse_domain(document.source_url),
                    document_type="scheme_page",
                    amc_name=document.amc_name,
                    scheme_name=document.scheme_name,
                    scheme_category=document.scheme_category,
                    section_id=section_id,
                    section_title=section_title,
                    answer_mode=answer_mode,
                    last_fetched_at=document.fetched_at.date().isoformat(),
                    content_hash=document.content_hash,
                    language="en",
                    token_count=token_count,
                )

                chunk = Chunk(
                    chunk_id=self._make_chunk_id(document.document_id, section_id, chunk_index),
                    document_id=document.document_id,
                    chunk_index=chunk_index,
                    text=enriched,
                    token_count=token_count,
                    metadata=metadata,
                )

                if self._validate_chunk(chunk):
                    chunks.append(chunk)
                    chunk_index += 1

        if not chunks:
            raise ValueError(f"No valid chunks produced for document {document.slug}")

        return chunks

    def chunk_document(self, document: ParsedDocument) -> ChunkResult:
        try:
            chunks = self.chunk(document)
            return ChunkResult(slug=document.slug, status="success", chunks=chunks)
        except Exception as exc:
            logger.exception("Chunking failed for %s: %s", document.slug, exc)
            return ChunkResult(slug=document.slug, status="failed", error=str(exc))

    def _collect_fields(self, document: ParsedDocument) -> dict[str, str]:
        fields: dict[str, str] = {}
        for section in document.sections:
            fields.update(section.fields)
        facts = document.facts.as_dict()
        for key, value in facts.items():
            if value:
                fields.setdefault(key, value)
        return fields

    def _build_chunk_bodies(
        self, document: ParsedDocument, fields: dict[str, str]
    ) -> list[tuple[str, str, str, str]]:
        bodies: list[tuple[str, str, str, str]] = []

        for section_id, section_title, group_fields in ATTRIBUTE_GROUPS.values():
            selected = {name: fields[name] for name in group_fields if name in fields}
            if not selected:
                continue
            bodies.append(
                (
                    section_id,
                    section_title,
                    fields_to_content(selected),
                    "link_only" if section_id in LINK_ONLY_SECTIONS else "factual",
                )
            )

        for section in document.sections:
            if section.section_id in PROSE_SECTIONS:
                bodies.append(
                    (section.section_id, section.title, section.content, "factual")
                )
            elif section.section_id in LINK_ONLY_SECTIONS:
                bodies.append(
                    (section.section_id, section.title, section.content, "link_only")
                )

        if fields.get("nav"):
            bodies.append(
                (
                    "performance",
                    "Performance & NAV",
                    (
                        f"NAV: {fields['nav']}\n"
                        "For historical returns and performance data, refer to the official Groww scheme page."
                    ),
                    "link_only",
                )
            )

        deduped: list[tuple[str, str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for section_id, title, body, mode in bodies:
            key = (section_id, body.strip())
            if key in seen or not body.strip():
                continue
            seen.add(key)
            deduped.append((section_id, title, body.strip(), mode))

        return deduped

    def _split_oversized_prose(self, body: str) -> list[str]:
        body_limit = max(50, self.settings.max_tokens - HEADER_TOKEN_OVERHEAD)
        if estimate_tokens(body) <= body_limit:
            return [body]

        sentences = split_sentences(body)
        if not sentences:
            return [body]

        parts: list[str] = []
        current: list[str] = []

        for sentence in sentences:
            candidate = " ".join(current + [sentence]).strip()
            if current and estimate_tokens(candidate) > body_limit:
                parts.append(" ".join(current).strip())
                overlap = self._tail_overlap(current)
                current = overlap + [sentence]
            else:
                current.append(sentence)

        if current:
            parts.append(" ".join(current).strip())

        return parts or [body]

    def _tail_overlap(self, sentences: list[str]) -> list[str]:
        if not sentences:
            return []
        overlap: list[str] = []
        for sentence in reversed(sentences):
            overlap.insert(0, sentence)
            if estimate_tokens(" ".join(overlap)) >= self.settings.overlap_tokens:
                break
        return overlap

    def _enrich(self, document: ParsedDocument, section_title: str, chunk_body: str) -> str:
        clean_body = strip_html(chunk_body)
        return self.settings.enrichment_template.format(
            scheme_name=document.scheme_name,
            scheme_category=document.scheme_category,
            section_title=section_title,
            source_url=document.source_url,
            chunk_body=clean_body,
        ).strip()

    def _should_keep_chunk(self, enriched: str, token_count: int) -> bool:
        if token_count >= self.settings.min_tokens:
            return True
        if token_count >= 15 and any(label in enriched for label in PRIORITY_FIELD_LABELS):
            return True
        return False

    def _validate_chunk(self, chunk: Chunk) -> bool:
        if chunk.metadata.source_url not in self._allowlist:
            logger.warning("Rejecting chunk with non-allowlisted URL: %s", chunk.metadata.source_url)
            return False
        if not chunk.metadata.scheme_name.strip():
            logger.warning("Rejecting chunk with empty scheme name")
            return False
        if not chunk.text.strip():
            return False
        if "<" in chunk.text and ">" in chunk.text:
            logger.warning("Rejecting chunk with residual HTML tags: %s", chunk.chunk_id)
            return False
        return True

    @staticmethod
    def _make_chunk_id(document_id: str, section_id: str, chunk_index: int) -> str:
        return str(uuid.uuid5(NAMESPACE_URL, f"{document_id}:{section_id}:{chunk_index}"))


def estimate_tokens(text: str) -> int:
    return len(re.findall(r"\S+", text))


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def fields_to_content(fields: dict[str, str]) -> str:
    lines = [
        f"{FIELD_LABELS.get(key, key.replace('_', ' ').title())}: {value}"
        for key, value in fields.items()
    ]
    return "\n".join(lines)


def strip_html(text: str) -> str:
    if "<" not in text:
        return text.strip()
    return BeautifulSoup(text, "html.parser").get_text("\n", strip=True)


def urlparse_domain(url: str) -> str:
    return urlparse(url).netloc
