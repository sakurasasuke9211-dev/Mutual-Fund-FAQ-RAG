from __future__ import annotations

import os
from pathlib import Path

import yaml

from generation.models import GenerationConfig
from ingestion.config import CONFIG_DIR

RAG_CONFIG_PATH = CONFIG_DIR / "rag.yaml"

PROVIDER_DEFAULTS = {
    "openai": {
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
    "groq": {
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
    },
}


def load_generation_config(config_path: Path | None = None) -> GenerationConfig:
    path = config_path or RAG_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        generation = yaml.safe_load(handle).get("rag", {}).get("generation", {})

    provider = os.getenv("LLM_PROVIDER", generation.get("provider", "groq")).strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider, {})

    return GenerationConfig(
        provider=provider,
        model=os.getenv(
            "LLM_MODEL",
            generation.get("model", defaults.get("model", "llama-3.3-70b-versatile")),
        ),
        temperature=float(os.getenv("LLM_TEMPERATURE", generation.get("temperature", 0.1))),
        max_sentences=int(os.getenv("LLM_MAX_SENTENCES", generation.get("max_sentences", 3))),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", generation.get("max_tokens", 256))),
        request_timeout_seconds=int(
            os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", generation.get("request_timeout_seconds", 30))
        ),
        base_url=os.getenv(
            "LLM_BASE_URL",
            generation.get("base_url", defaults.get("base_url", "")),
        ).rstrip("/"),
    )
