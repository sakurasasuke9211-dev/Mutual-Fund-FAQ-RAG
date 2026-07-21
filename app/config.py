from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from ingestion.config import CONFIG_DIR, DATA_DIR

API_CONFIG_PATH = CONFIG_DIR / "api.yaml"
DEFAULT_THREAD_DB_PATH = DATA_DIR / "threads.db"


@dataclass(frozen=True)
class APIConfig:
    max_context_turns: int
    title: str
    version: str
    thread_store: str
    thread_db_path: Path
    cors_allowed_origins: tuple[str, ...]


def load_api_config(config_path: Path | None = None) -> APIConfig:
    path = config_path or API_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle).get("api", {})

    configured_origins = data.get(
        "cors_allowed_origins",
        ["http://localhost:5173", "http://127.0.0.1:5173"],
    )
    env_origins = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    cors_allowed_origins = (
        tuple(origin.strip() for origin in env_origins.split(",") if origin.strip())
        if env_origins
        else tuple(str(origin) for origin in configured_origins)
    )

    return APIConfig(
        max_context_turns=int(os.getenv("API_MAX_CONTEXT_TURNS", data.get("max_context_turns", 3))),
        title=os.getenv("API_TITLE", data.get("title", "Mutual Fund FAQ Assistant API")),
        version=os.getenv("API_VERSION", data.get("version", "1.0.0")),
        thread_store=os.getenv("THREAD_STORE", data.get("thread_store", "sqlite")).strip().lower(),
        thread_db_path=Path(
            os.getenv("THREAD_DB_PATH", data.get("thread_db_path", str(DEFAULT_THREAD_DB_PATH)))
        ),
        cors_allowed_origins=cors_allowed_origins,
    )
