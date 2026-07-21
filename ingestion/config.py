from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INDEX_DATA_DIR = DATA_DIR / "index"
FACTS_DATA_DIR = DATA_DIR / "facts"
LOGS_DIR = PROJECT_ROOT / "logs" / "ingestion"

MANIFEST_PATH = CONFIG_DIR / "corpus_manifest.yaml"
ENV_FILE_PATH = PROJECT_ROOT / ".env"

USER_AGENT = "MutualFundFAQBot/1.0 (+https://github.com/mutual-fund-faq-rag)"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAYS = (2, 4, 8)
DEFAULT_RATE_LIMIT_SECONDS = 1.5

# Canonical keys for the five priority fund metrics
FUND_FACT_FIELDS = (
    "nav",
    "expense_ratio",
    "minimum_sip",
    "fund_size",
    "rating",
)

# Keywords indicating a Groww fund page rendered successfully
FUND_PAGE_MARKERS = (
    "expense ratio",
    "exit load",
    "minimum sip",
    "riskometer",
    "benchmark",
)


@dataclass(frozen=True)
class ScraperSettings:
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delays: tuple[int, ...] = DEFAULT_RETRY_DELAYS
    rate_limit_seconds: float = DEFAULT_RATE_LIMIT_SECONDS
    user_agent: str = USER_AGENT
    raw_data_dir: Path = RAW_DATA_DIR
    use_playwright_fallback: bool = True


def get_scraper_settings() -> ScraperSettings:
    return ScraperSettings(
        raw_data_dir=Path(os.getenv("RAW_DATA_DIR", str(RAW_DATA_DIR))),
        use_playwright_fallback=os.getenv("USE_PLAYWRIGHT_FALLBACK", "true").lower()
        == "true",
    )


def load_env_file() -> None:
    """Load variables from `.env` in the project root if present."""
    if not ENV_FILE_PATH.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ENV_FILE_PATH, override=False)
