from __future__ import annotations

import re

from citation.models import Citation
from guardrails.models import GuardrailsConfig, ResponseValidation
from ingestion.manifest import allowed_urls, load_manifest

ADVISORY_ANSWER_PATTERNS = (
    r"\byou should invest\b",
    r"\byou should (?:buy|sell|hold|redeem|switch)\b",
    r"\bi recommend\b",
    r"\brecommend investing\b",
    r"\bgood to invest\b",
    r"\bgood investment\b",
    r"\bsafe investment\b",
    r"\bsuitable for (?:you|your)\b",
    r"\bworth (?:it|investing|buying)\b",
    r"\bbetter (fund|option|choice)\b",
    r"\bwill outperform\b",
    r"\boutperform\b",
    r"\bbuy this fund\b",
    r"\bsell this fund\b",
    r"\binvest (?:now|today)\b",
)

PERFORMANCE_COMPARISON_PATTERNS = (
    r"\bhigher returns than\b",
    r"\bbetter returns than\b",
    r"\bbeats (the|this|that)\b",
    r"\boutperforms\b",
)


class ResponseValidator:
    """Post-generation response guardrail."""

    def __init__(self, config: GuardrailsConfig | None = None) -> None:
        from guardrails.config import load_guardrails_config

        self.config = config or load_guardrails_config()
        self._allowed_urls = allowed_urls(load_manifest())

    def validate(
        self,
        answer: str,
        citation: Citation,
        *,
        max_sentences: int | None = None,
    ) -> ResponseValidation:
        limit = max_sentences if max_sentences is not None else self.config.max_sentences
        cleaned = answer.strip()
        if not cleaned:
            return ResponseValidation(valid=False, reason="empty_answer")

        if citation.source_url not in self._allowed_urls:
            return ResponseValidation(valid=False, reason="citation_not_allowlisted")

        if not citation.last_updated.strip():
            return ResponseValidation(valid=False, reason="missing_last_updated")

        urls_in_answer = re.findall(r"https?://[^\s)>\"]+", cleaned)
        if urls_in_answer:
            return ResponseValidation(valid=False, reason="url_in_answer_text")

        normalized = cleaned.lower()
        for pattern in ADVISORY_ANSWER_PATTERNS:
            if re.search(pattern, normalized):
                return ResponseValidation(valid=False, reason="advisory_language")

        for pattern in PERFORMANCE_COMPARISON_PATTERNS:
            if re.search(pattern, normalized):
                return ResponseValidation(valid=False, reason="performance_comparison")

        sentences = self._split_sentences(cleaned)
        if len(sentences) > limit:
            sanitized = " ".join(sentences[:limit])
            return ResponseValidation(valid=True, reason="truncated_sentences", sanitized_answer=sanitized)

        return ResponseValidation(valid=True)

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [part.strip() for part in parts if part.strip()]
