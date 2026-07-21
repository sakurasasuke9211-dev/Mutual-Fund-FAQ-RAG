from __future__ import annotations

import os
from pathlib import Path

import yaml

from guardrails.models import GuardrailsConfig
from ingestion.config import CONFIG_DIR

GUARDRAILS_CONFIG_PATH = CONFIG_DIR / "guardrails.yaml"


def load_guardrails_config(config_path: Path | None = None) -> GuardrailsConfig:
    path = config_path or GUARDRAILS_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle).get("guardrails", {})

    return GuardrailsConfig(
        max_query_length=int(os.getenv("GUARDRAILS_MAX_QUERY_LENGTH", data.get("max_query_length", 500))),
        max_sentences=int(os.getenv("GUARDRAILS_MAX_SENTENCES", data.get("max_sentences", 3))),
        advisory_phrases=_tuple_from_env_or_yaml(
            "GUARDRAILS_ADVISORY_PHRASES",
            data.get("advisory_phrases", []),
        ),
        comparison_phrases=_tuple_from_env_or_yaml(
            "GUARDRAILS_COMPARISON_PHRASES",
            data.get("comparison_phrases", []),
        ),
        performance_opinion_phrases=_tuple_from_env_or_yaml(
            "GUARDRAILS_PERFORMANCE_OPINION_PHRASES",
            data.get("performance_opinion_phrases", []),
        ),
    )


def _tuple_from_env_or_yaml(env_key: str, yaml_values: list) -> tuple[str, ...]:
    env_value = os.getenv(env_key, "").strip()
    if env_value:
        return tuple(phrase.strip().lower() for phrase in env_value.split(",") if phrase.strip())
    return tuple(str(item).strip().lower() for item in yaml_values if str(item).strip())
