from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

QueryDecisionReason = Literal[
    "pass",
    "empty",
    "too_long",
    "pii",
    "advisory",
    "comparison",
    "performance_opinion",
]

RefusalCategory = Literal[
    "pii",
    "advisory",
    "performance_opinion",
    "insufficient_sources",
    "response_blocked",
]


@dataclass(frozen=True)
class GuardrailsConfig:
    max_query_length: int
    max_sentences: int
    advisory_phrases: tuple[str, ...]
    comparison_phrases: tuple[str, ...]
    performance_opinion_phrases: tuple[str, ...]


@dataclass(frozen=True)
class QueryClassification:
    allowed: bool
    reason: QueryDecisionReason
    message: str = ""


@dataclass(frozen=True)
class ResponseValidation:
    valid: bool
    reason: str = ""
    sanitized_answer: str | None = None


@dataclass(frozen=True)
class EducationalLink:
    label: str
    url: str


@dataclass(frozen=True)
class GuardedResponse:
    query: str
    response_type: Literal["answer", "refusal"]
    answer: str
    source_url: str | None = None
    source_title: str | None = None
    last_updated: str | None = None
    educational_link: EducationalLink | None = None
    chunk_ids: list[str] | None = None
    query_reason: QueryDecisionReason | None = None
    refusal_category: RefusalCategory | None = None
