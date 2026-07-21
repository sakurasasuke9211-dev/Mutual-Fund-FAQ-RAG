from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from ingestion.config import FUND_PAGE_MARKERS, ScraperSettings, get_scraper_settings
from ingestion.models import SchemeEntry, ScrapeResult
from ingestion.logging_config import utc_now

logger = logging.getLogger("ingestion.scraper")

REMOVABLE_TAGS = ("script", "style", "noscript", "svg", "iframe")


class GrowwScrapingService:
    """Fetch and persist latest HTML for Groww mutual fund scheme pages."""

    def __init__(self, settings: ScraperSettings | None = None) -> None:
        self.settings = settings or get_scraper_settings()
        self.settings.raw_data_dir.mkdir(parents=True, exist_ok=True)

    def scrape_all(self, schemes: list[SchemeEntry]) -> list[ScrapeResult]:
        results: list[ScrapeResult] = []
        for index, scheme in enumerate(schemes):
            if index > 0:
                time.sleep(self.settings.rate_limit_seconds)
            results.append(self.scrape_url(scheme))
        return results

    def scrape_url(self, scheme: SchemeEntry) -> ScrapeResult:
        fetched_at = utc_now()
        logger.info("Scraping %s (%s)", scheme.name, scheme.url)

        try:
            html, http_status, used_playwright = self._fetch_with_retries(scheme.url)
            self._validate_response(scheme, html, http_status)

            normalized_html = self.normalize_html(html)
            if not self._contains_fund_markers(normalized_html):
                if self.settings.use_playwright_fallback and not used_playwright:
                    logger.warning(
                        "Static HTML missing fund markers for %s; retrying with Playwright",
                        scheme.slug,
                    )
                    html = self._fetch_with_playwright(scheme.url)
                    normalized_html = self.normalize_html(html)
                    self._validate_response(scheme, html, 200)
                if not self._contains_fund_markers(normalized_html):
                    raise ValueError(
                        "Fetched page does not contain expected mutual fund content markers"
                    )

            content_hash = self.compute_hash(normalized_html)
            previous_hash = self._read_latest_hash(scheme.slug)
            content_changed = previous_hash != content_hash

            raw_path, normalized_path = self._persist_snapshot(
                scheme=scheme,
                fetched_at=fetched_at,
                raw_html=html,
                normalized_html=normalized_html,
                content_hash=content_hash,
                http_status=http_status,
                used_playwright=used_playwright,
            )

            logger.info(
                "Scraped %s successfully (changed=%s, hash=%s)",
                scheme.slug,
                content_changed,
                content_hash[:12],
            )

            return ScrapeResult(
                url=scheme.url,
                slug=scheme.slug,
                scheme_name=scheme.name,
                status="success",
                http_status=http_status,
                fetched_at=fetched_at,
                content_hash=content_hash,
                raw_path=str(raw_path),
                normalized_path=str(normalized_path),
                content_changed=content_changed,
            )
        except Exception as exc:
            logger.exception("Failed to scrape %s: %s", scheme.slug, exc)
            return ScrapeResult(
                url=scheme.url,
                slug=scheme.slug,
                scheme_name=scheme.name,
                status="failed",
                http_status=None,
                fetched_at=fetched_at,
                content_hash=None,
                raw_path=None,
                normalized_path=None,
                content_changed=False,
                error=str(exc),
            )

    def _fetch_with_retries(self, url: str) -> tuple[str, int, bool]:
        last_error: Exception | None = None

        for attempt in range(1, self.settings.max_retries + 1):
            try:
                html, status = self._fetch_with_httpx(url)
                return html, status, False
            except Exception as exc:
                last_error = exc
                if attempt < self.settings.max_retries:
                    delay = self.settings.retry_delays[
                        min(attempt - 1, len(self.settings.retry_delays) - 1)
                    ]
                    logger.warning(
                        "Attempt %s/%s failed for %s: %s. Retrying in %ss",
                        attempt,
                        self.settings.max_retries,
                        url,
                        exc,
                        delay,
                    )
                    time.sleep(delay)

        if (
            self.settings.use_playwright_fallback
            and last_error is not None
            and "403" in str(last_error)
        ):
            logger.warning("HTTP fetch blocked for %s; falling back to Playwright", url)
            return self._fetch_with_playwright(url), 200, True

        raise RuntimeError(f"Failed to fetch {url} after retries") from last_error

    def _fetch_with_httpx(self, url: str) -> tuple[str, int]:
        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-IN, en;q=0.9",
        }
        with httpx.Client(
            timeout=self.settings.timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            text = response.text
            if not text.strip():
                raise ValueError("Empty HTML response body")
            return text, response.status_code

    def _fetch_with_playwright(self, url: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for JS-rendered fallback but is not installed"
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self.settings.user_agent)
            page.goto(url, wait_until="networkidle", timeout=self.settings.timeout_seconds * 1000)
            html = page.content()
            browser.close()

        if not html.strip():
            raise ValueError("Playwright returned empty HTML")
        return html

    @staticmethod
    def normalize_html(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag_name in REMOVABLE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        text = soup.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def compute_hash(normalized_content: str) -> str:
        return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()

    @staticmethod
    def _contains_fund_markers(normalized_content: str) -> bool:
        lowered = normalized_content.lower()
        return any(marker in lowered for marker in FUND_PAGE_MARKERS)

    @staticmethod
    def _validate_response(scheme: SchemeEntry, html: str, http_status: int) -> None:
        if http_status != 200:
            raise ValueError(f"Unexpected HTTP status: {http_status}")
        if not html.strip():
            raise ValueError("Empty HTML body")
        if scheme.slug not in scheme.url:
            raise ValueError(f"Scheme slug '{scheme.slug}' not present in URL")

    def _scheme_dir(self, slug: str) -> Path:
        return self.settings.raw_data_dir / slug

    def _read_latest_hash(self, slug: str) -> str | None:
        latest_file = self._scheme_dir(slug) / "latest.json"
        if not latest_file.exists():
            return None
        with latest_file.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload.get("content_hash")

    def _persist_snapshot(
        self,
        scheme: SchemeEntry,
        fetched_at: datetime,
        raw_html: str,
        normalized_html: str,
        content_hash: str,
        http_status: int,
        used_playwright: bool,
    ) -> tuple[Path, Path]:
        scheme_dir = self._scheme_dir(scheme.slug)
        scheme_dir.mkdir(parents=True, exist_ok=True)

        timestamp = fetched_at.astimezone().strftime("%Y-%m-%d_%H-%M-%S")
        raw_path = scheme_dir / f"{timestamp}.html"
        normalized_path = scheme_dir / f"{timestamp}.normalized.txt"
        meta_path = scheme_dir / f"{timestamp}.meta.json"

        raw_path.write_text(raw_html, encoding="utf-8")
        normalized_path.write_text(normalized_html, encoding="utf-8")

        metadata = {
            "url": scheme.url,
            "slug": scheme.slug,
            "scheme_name": scheme.name,
            "scheme_category": scheme.category,
            "fetched_at": fetched_at.isoformat(),
            "http_status": http_status,
            "content_hash": content_hash,
            "used_playwright": used_playwright,
            "raw_path": str(raw_path),
            "normalized_path": str(normalized_path),
        }
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        latest_payload = {
            **metadata,
            "meta_path": str(meta_path),
        }
        (scheme_dir / "latest.json").write_text(
            json.dumps(latest_payload, indent=2), encoding="utf-8"
        )

        return raw_path, normalized_path
