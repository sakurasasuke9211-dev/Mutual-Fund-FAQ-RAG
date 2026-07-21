from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from ingestion.config import FUND_FACT_FIELDS
from ingestion.facts_store import FundFactsStore
from ingestion.models import (
    FundFacts,
    ParsedDocument,
    ParsedSection,
    ParseResult,
    SchemeEntry,
    ScrapeResult,
)

logger = logging.getLogger("ingestion.parser")

NAMESPACE_URL = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

LABEL_FIELD_MAP = {
    "expense ratio": "expense_ratio",
    "min. for sip": "minimum_sip",
    "minimum sip": "minimum_sip",
    "fund size (aum)": "fund_size",
    "fund size": "fund_size",
    "total aum": "fund_size",
    "rating": "rating",
    "nav": "nav",
    "fund benchmark": "benchmark",
    "exit load": "exit_load",
    "risk": "riskometer",
}

TEXT_FALLBACK_PATTERNS = {
    "nav": re.compile(r"NAV(?:\s*:\s*[^|₹\n]*)?\s*(₹[\d,.]+)", re.IGNORECASE),
    "expense_ratio": re.compile(r"Expense ratio\s*[|:\n]?\s*([\d.]+%)", re.IGNORECASE),
    "minimum_sip": re.compile(
        r"(?:Min(?:\.|imum)?\.?\s*for\s*SIP|Minimum SIP Investment is set to)\s*[|:\n]?\s*(₹[\d,.]+)",
        re.IGNORECASE,
    ),
    "fund_size": re.compile(
        r"(?:Fund size(?: \(AUM\))?|Total AUM)\s*[|:\n]?\s*(₹[\d,.]+ ?(?:Cr|L)?\.?)",
        re.IGNORECASE,
    ),
    "rating": re.compile(r"(?<![\w])Rating\s*[|:\n]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    "exit_load": re.compile(r"Exit load(?: of)?\s*([^|;.\n]+)", re.IGNORECASE),
    "benchmark": re.compile(r"Fund benchmark\s*[|:\n]?\s*([^\n|]+)", re.IGNORECASE),
    "riskometer": re.compile(r"rated\s+([^|.]+?\s+risk)", re.IGNORECASE),
}


class GrowwHtmlParser:
    """Parse Groww mutual fund scheme pages into structured sections and fund facts."""

    def __init__(self, parsed_dir: Path | None = None) -> None:
        self.parsed_dir = parsed_dir or Path(__file__).resolve().parent.parent / "data" / "parsed"
        self.parsed_dir.mkdir(parents=True, exist_ok=True)

    def parse_scrape_result(
        self,
        scheme: SchemeEntry,
        scrape_result: ScrapeResult,
        amc_name: str,
    ) -> ParseResult:
        if scrape_result.status != "success" or not scrape_result.raw_path:
            return ParseResult(
                slug=scheme.slug,
                status="failed",
                error="Scrape did not succeed; parser skipped.",
            )

        try:
            document = self.parse_file(
                html_path=Path(scrape_result.raw_path),
                scheme=scheme,
                amc_name=amc_name,
                fetched_at=scrape_result.fetched_at,
                content_hash=scrape_result.content_hash or "",
            )
            self._persist_document(document)
            return ParseResult(slug=scheme.slug, status="success", document=document)
        except Exception as exc:
            logger.exception("Failed to parse %s: %s", scheme.slug, exc)
            return ParseResult(slug=scheme.slug, status="failed", error=str(exc))

    def parse_file(
        self,
        html_path: Path,
        scheme: SchemeEntry,
        amc_name: str,
        fetched_at: datetime,
        content_hash: str,
    ) -> ParsedDocument:
        html = html_path.read_text(encoding="utf-8")
        return self.parse_html(
            html=html,
            scheme=scheme,
            amc_name=amc_name,
            fetched_at=fetched_at,
            content_hash=content_hash,
        )

    def parse_html(
        self,
        html: str,
        scheme: SchemeEntry,
        amc_name: str,
        fetched_at: datetime,
        content_hash: str,
    ) -> ParsedDocument:
        soup = BeautifulSoup(html, "html.parser")
        fields = self._extract_fields(soup)
        facts = self._build_fund_facts(
            scheme=scheme,
            fields=fields,
            fetched_at=fetched_at,
            content_hash=content_hash,
        )
        sections = self._build_sections(soup, fields)
        document_id = str(uuid.uuid5(NAMESPACE_URL, scheme.slug))

        return ParsedDocument(
            document_id=document_id,
            slug=scheme.slug,
            scheme_name=scheme.name,
            scheme_category=scheme.category,
            source_url=scheme.url,
            amc_name=amc_name,
            fetched_at=fetched_at,
            content_hash=content_hash,
            sections=sections,
            facts=facts,
        )

    def _extract_fields(self, soup: BeautifulSoup) -> dict[str, str]:
        fields: dict[str, str] = {}

        for row in soup.select(".flex.flex-column"):
            spans = row.find_all("span", recursive=False)
            if len(spans) < 2:
                continue
            label = spans[0].get_text(" ", strip=True)
            value = spans[1].get_text(" ", strip=True)
            field_key = self._map_label_to_field(label)
            if field_key and value:
                fields[field_key] = self._clean_value(value)

        page_text = soup.get_text("\n", strip=True)
        for field_key, pattern in TEXT_FALLBACK_PATTERNS.items():
            if field_key in fields:
                continue
            match = pattern.search(page_text)
            if match:
                fields[field_key] = self._clean_value(match.group(1))

        return fields

    def _build_fund_facts(
        self,
        scheme: SchemeEntry,
        fields: dict[str, str],
        fetched_at: datetime,
        content_hash: str,
    ) -> FundFacts:
        return FundFacts(
            slug=scheme.slug,
            scheme_name=scheme.name,
            scheme_category=scheme.category,
            source_url=scheme.url,
            nav=fields.get("nav"),
            expense_ratio=fields.get("expense_ratio"),
            minimum_sip=fields.get("minimum_sip"),
            fund_size=fields.get("fund_size"),
            rating=fields.get("rating"),
            fetched_at=fetched_at,
            content_hash=content_hash,
        )

    def _build_sections(
        self, soup: BeautifulSoup, fields: dict[str, str]
    ) -> list[ParsedSection]:
        sections: list[ParsedSection] = []

        fund_detail_fields = {
            key: fields[key]
            for key in ("nav", "expense_ratio", "minimum_sip", "fund_size", "rating")
            if key in fields
        }
        if fund_detail_fields:
            sections.append(
                ParsedSection(
                    section_id="fund_details",
                    title="Fund Details",
                    content=self._fields_to_content(fund_detail_fields),
                    fields=fund_detail_fields,
                )
            )

        fees_fields = {
            key: fields[key]
            for key in ("expense_ratio", "exit_load")
            if key in fields
        }
        if fees_fields:
            sections.append(
                ParsedSection(
                    section_id="fees_and_loads",
                    title="Fees & Loads",
                    content=self._fields_to_content(fees_fields),
                    fields=fees_fields,
                )
            )

        benchmark_fields = {
            key: fields[key]
            for key in ("benchmark", "riskometer")
            if key in fields
        }
        if benchmark_fields:
            sections.append(
                ParsedSection(
                    section_id="benchmark_and_risk",
                    title="Benchmark & Risk",
                    content=self._fields_to_content(benchmark_fields),
                    fields=benchmark_fields,
                )
            )

        objective = self._extract_investment_objective(soup)
        if objective:
            sections.append(
                ParsedSection(
                    section_id="overview",
                    title="Investment Objective",
                    content=objective,
                    fields={"investment_objective": objective},
                )
            )

        if not sections:
            raise ValueError("No parseable fund sections found in HTML")

        return sections

    @staticmethod
    def _extract_investment_objective(soup: BeautifulSoup) -> str | None:
        heading = soup.find(
            lambda tag: tag.name in {"h3", "h4", "span", "div"}
            and tag.get_text(strip=True).lower() == "investment objective"
        )
        if not heading:
            return None
        container = heading.find_parent("div")
        if not container:
            return None
        text = container.get_text(" ", strip=True)
        text = re.sub(r"^Investment Objective\s*", "", text, flags=re.IGNORECASE)
        return text.strip() or None

    @staticmethod
    def _map_label_to_field(label: str) -> str | None:
        normalized = re.sub(r"\s+", " ", label.strip().lower())
        if normalized.startswith("nav"):
            return "nav"
        return LABEL_FIELD_MAP.get(normalized)

    @staticmethod
    def _clean_value(value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value.strip())
        cleaned = cleaned.rstrip(".")
        return cleaned

    @staticmethod
    def _fields_to_content(fields: dict[str, str]) -> str:
        labels = {
            "nav": "NAV",
            "expense_ratio": "Expense Ratio",
            "minimum_sip": "Minimum SIP",
            "fund_size": "Fund Size",
            "rating": "Rating",
            "exit_load": "Exit Load",
            "benchmark": "Benchmark",
            "riskometer": "Riskometer",
        }
        lines = [f"{labels.get(key, key)}: {value}" for key, value in fields.items()]
        return "\n".join(lines)

    def _persist_document(self, document: ParsedDocument) -> Path:
        scheme_dir = self.parsed_dir / document.slug
        scheme_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "document_id": document.document_id,
            "slug": document.slug,
            "scheme_name": document.scheme_name,
            "scheme_category": document.scheme_category,
            "source_url": document.source_url,
            "amc_name": document.amc_name,
            "fetched_at": document.fetched_at.isoformat(),
            "content_hash": document.content_hash,
            "facts": document.facts.as_dict(),
            "sections": [
                {
                    "section_id": section.section_id,
                    "title": section.title,
                    "content": section.content,
                    "fields": section.fields,
                }
                for section in document.sections
            ],
        }

        latest_path = scheme_dir / "latest.json"
        latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return latest_path


def parse_and_store_facts(
    scheme: SchemeEntry,
    scrape_result: ScrapeResult,
    amc_name: str,
    facts_store: FundFactsStore | None = None,
    parser: GrowwHtmlParser | None = None,
) -> ParseResult:
    parser = parser or GrowwHtmlParser()
    facts_store = facts_store or FundFactsStore()
    parse_result = parser.parse_scrape_result(scheme, scrape_result, amc_name)

    if parse_result.status == "success" and parse_result.document is not None:
        facts_store.save(parse_result.document.facts)
        missing = parse_result.document.facts.missing_fields()
        if missing:
            logger.warning(
                "Parsed %s but missing priority fields: %s",
                scheme.slug,
                ", ".join(missing),
            )

    return parse_result
