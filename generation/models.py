from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationConfig:
    provider: str
    model: str
    temperature: float
    max_sentences: int
    max_tokens: int
    request_timeout_seconds: int
    base_url: str = ""
