from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ingestion.config import FACTS_DATA_DIR, FUND_FACT_FIELDS
from ingestion.models import FundFacts


class FundFactsStore:
    """Persist structured fund metrics (NAV, expense ratio, etc.) separately from RAG chunks."""

    def __init__(self, facts_dir: Path | None = None) -> None:
        self.facts_dir = facts_dir or FACTS_DATA_DIR
        self.facts_dir.mkdir(parents=True, exist_ok=True)

    def save(self, facts: FundFacts) -> Path:
        scheme_dir = self.facts_dir / facts.slug
        scheme_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "slug": facts.slug,
            "scheme_name": facts.scheme_name,
            "scheme_category": facts.scheme_category,
            "source_url": facts.source_url,
            "fetched_at": facts.fetched_at.isoformat(),
            "content_hash": facts.content_hash,
            "facts": facts.as_dict(),
        }

        timestamp = facts.fetched_at.astimezone().strftime("%Y-%m-%d_%H-%M-%S")
        history_path = scheme_dir / "history" / f"{timestamp}.json"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path = scheme_dir / "latest.json"

        history_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._refresh_catalog()
        return latest_path

    def load_latest(self, slug: str) -> FundFacts | None:
        latest_path = self.facts_dir / slug / "latest.json"
        if not latest_path.exists():
            return None
        with latest_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        return self._from_payload(payload)

    def load_all_latest(self) -> list[FundFacts]:
        catalog_path = self.facts_dir / "catalog.json"
        if not catalog_path.exists():
            return []
        with catalog_path.open(encoding="utf-8") as handle:
            catalog = json.load(handle)
        results: list[FundFacts] = []
        for slug in catalog.get("slugs", []):
            facts = self.load_latest(slug)
            if facts is not None:
                results.append(facts)
        return results

    def get_fact(self, slug: str, field: str) -> str | None:
        if field not in FUND_FACT_FIELDS:
            raise KeyError(f"Unsupported fact field: {field}")
        facts = self.load_latest(slug)
        if facts is None:
            return None
        return facts.as_dict()[field]

    def _refresh_catalog(self) -> None:
        slugs = sorted(
            path.name
            for path in self.facts_dir.iterdir()
            if path.is_dir() and (path / "latest.json").exists()
        )
        catalog = {
            "updated_at": datetime.now().astimezone().isoformat(),
            "slugs": slugs,
            "fields": list(FUND_FACT_FIELDS),
        }
        (self.facts_dir / "catalog.json").write_text(
            json.dumps(catalog, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _from_payload(payload: dict) -> FundFacts:
        facts = payload.get("facts", {})
        return FundFacts(
            slug=str(payload["slug"]),
            scheme_name=str(payload["scheme_name"]),
            scheme_category=str(payload["scheme_category"]),
            source_url=str(payload["source_url"]),
            nav=facts.get("nav"),
            expense_ratio=facts.get("expense_ratio"),
            minimum_sip=facts.get("minimum_sip"),
            fund_size=facts.get("fund_size"),
            rating=facts.get("rating"),
            fetched_at=datetime.fromisoformat(str(payload["fetched_at"])),
            content_hash=str(payload["content_hash"]),
        )

    @staticmethod
    def facts_to_chunk_text(facts: FundFacts) -> str:
        """Human-readable block used for RAG chunking and embedding."""
        lines = [
            f"Scheme: {facts.scheme_name}",
            f"Category: {facts.scheme_category}",
            f"Source: {facts.source_url}",
            "",
            "Key fund metrics:",
            f"NAV: {facts.nav or 'Not available'}",
            f"Expense Ratio: {facts.expense_ratio or 'Not available'}",
            f"Minimum SIP: {facts.minimum_sip or 'Not available'}",
            f"Fund Size: {facts.fund_size or 'Not available'}",
            f"Rating: {facts.rating or 'Not available'}",
        ]
        return "\n".join(lines)
