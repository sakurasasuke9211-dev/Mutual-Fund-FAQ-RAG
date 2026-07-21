from __future__ import annotations

import re

from guardrails.models import GuardrailsConfig, QueryClassification, QueryDecisionReason

# India PAN: 5 letters + 4 digits + 1 letter
PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
# Aadhaar: 12 digits (allow spaced/dashed forms)
AADHAAR_PATTERN = re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b")
OTP_PATTERN = re.compile(r"\b(?:otp|one[\s-]?time[\s-]?password)\b", re.IGNORECASE)
ACCOUNT_NUMBER_PATTERN = re.compile(r"\b(?:account|a/c|acc)[\s#:.-]*\d{6,}\b", re.IGNORECASE)

ADVISORY_QUERY_PATTERNS = (
    # Direct requests to make an investment decision.
    r"\b(?:should|would|could|can|do)\s+(?:i|we)\s+(?:invest|buy|sell|hold|redeem|switch)\b",
    r"\bwould\s+you\s+(?:invest|buy|sell|hold|choose|pick)\b",
    r"\b(?:tell|advise)\s+me\s+(?:if|whether|what|which|when|where|how)\b",
    r"\b(?:recommend|recommendation|suggest|advice|advise)\b",
    r"\b(?:which|what)\s+(?:fund|scheme|option).{0,40}\b(?:choose|pick|buy|invest|best|better)\b",
    # Quality, suitability, and "worth it" judgments.
    r"\b(?:good|bad|safe|right|wise|smart|suitable)\s+to\s+(?:invest|buy|hold)\b",
    r"\b(?:good|bad|safe|right|wise|smart|suitable)\s+(?:fund|scheme|investment|choice|option)\b",
    r"\bworth\s+(?:it|buying|investing|holding)\b",
    r"\b(?:is|would)\s+(?:it|this|that)(?:\s+(?:fund|scheme))?\s+(?:be\s+)?(?:good|bad|safe|right|wise|smart|suitable)\b",
    r"\bsuitable\s+for\s+(?:me|my|us|our)\b",
    r"\bfit\s+(?:for|with)\s+(?:me|my|us|our)\b",
    r"\b(?:suit|suits|match|matches)\s+my\s+(?:risk|goal|portfolio|needs?|profile|retirement)\b",
    r"\bbest\s+for\s+(?:me|my|us|our)\b",
    # Personal allocation and timing decisions.
    r"\bhow much\s+should\s+(?:i|we)\s+(?:invest|allocate|put)\b",
    r"\bwhat (?:amount|percentage)\s+should\s+(?:i|we)\s+(?:invest|allocate|put)\b",
    r"\b(?:when|where)\s+should\s+(?:i|we)\s+(?:invest|buy|sell|redeem|switch)\b",
    r"\b(?:is|would)\s+(?:now|today|this week|this month)\s+(?:a\s+)?good time\b",
    r"\b(?:enter|exit|buy|sell|invest|redeem)\s+(?:now|today)\b",
    # Personalized suitability based on circumstances or goals.
    r"\b(?:for|given)\s+my\s+(?:age|income|salary|risk|goal|portfolio|retirement|tax|time horizon)\b",
    r"\b(?:meet|achieve|reach)\s+my\s+(?:goal|target|retirement)\b",
    r"\b(?:build|create|design).{0,25}\bportfolio\b",
    r"\bportfolio allocation\b",
)

PERFORMANCE_QUERY_PATTERNS = (
    r"\b(?:expected|estimated|projected|future|target|guaranteed)\s+returns?\b",
    r"\breturn\s+potential\b",
    r"\bwhat returns?\s+(?:can|should|will|would)\s+(?:i|we)\s+expect\b",
    r"\bhow much (?:return|profit|money)\b",
    r"\b(?:will|would|can|could)\s+(?:it|this|that|the fund|the scheme).{0,40}\b(?:outperform|beat|grow|rise|increase|deliver|give|return)\b",
    r"\b(?:will|would)\s+(?:i|we)\s+(?:make|earn|get)\b",
)


class QueryClassifier:
    """Pre-retrieval rule-based query guardrail."""

    def __init__(self, config: GuardrailsConfig | None = None) -> None:
        from guardrails.config import load_guardrails_config

        self.config = config or load_guardrails_config()

    def classify(self, query: str) -> QueryClassification:
        cleaned = query.strip()
        if not cleaned:
            return QueryClassification(
                allowed=False,
                reason="empty",
                message="Query must not be empty.",
            )

        if len(cleaned) > self.config.max_query_length:
            return QueryClassification(
                allowed=False,
                reason="too_long",
                message=f"Query exceeds maximum length of {self.config.max_query_length} characters.",
            )

        pii_reason = self._detect_pii(cleaned)
        if pii_reason:
            return QueryClassification(
                allowed=False,
                reason="pii",
                message="Queries containing personal or account information cannot be processed.",
            )

        normalized = re.sub(r"\s+", " ", cleaned.lower())

        if self._contains_phrase(normalized, self.config.advisory_phrases) or self._matches_patterns(
            normalized, ADVISORY_QUERY_PATTERNS
        ):
            return QueryClassification(
                allowed=False,
                reason="advisory",
                message="Investment advice and recommendation requests are not supported.",
            )

        if self._contains_phrase(normalized, self.config.comparison_phrases):
            if self._looks_like_fund_comparison(normalized):
                return QueryClassification(
                    allowed=False,
                    reason="comparison",
                    message="Comparative questions that imply a recommendation are not supported.",
                )

        if self._contains_phrase(
            normalized, self.config.performance_opinion_phrases
        ) or self._matches_patterns(normalized, PERFORMANCE_QUERY_PATTERNS):
            return QueryClassification(
                allowed=False,
                reason="performance_opinion",
                message="Performance predictions and opinions are not supported.",
            )

        return QueryClassification(allowed=True, reason="pass")

    @staticmethod
    def _detect_pii(text: str) -> QueryDecisionReason | None:
        if PAN_PATTERN.search(text):
            return "pii"
        if AADHAAR_PATTERN.search(text):
            return "pii"
        if EMAIL_PATTERN.search(text):
            return "pii"
        if PHONE_PATTERN.search(text):
            return "pii"
        if OTP_PATTERN.search(text):
            return "pii"
        if ACCOUNT_NUMBER_PATTERN.search(text):
            return "pii"
        return None

    @staticmethod
    def _contains_phrase(normalized_query: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in normalized_query for phrase in phrases)

    @staticmethod
    def _matches_patterns(normalized_query: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, normalized_query) for pattern in patterns)

    @staticmethod
    def _looks_like_fund_comparison(normalized_query: str) -> bool:
        comparison_markers = (" or ", " vs ", " versus ", "compare", "better")
        fund_markers = ("fund", "elss", "scheme", "large cap", "mid cap", "invest")
        has_comparison = any(marker in normalized_query for marker in comparison_markers)
        has_fund_context = any(marker in normalized_query for marker in fund_markers)
        return has_comparison and has_fund_context
