from __future__ import annotations

import re

from app.services.thread_manager import StoredMessage
from retrieval.filters import detect_metadata_filters

CONTEXT_REFERENCE_PATTERNS = (
    r"\bwhat about\b",
    r"\bhow about\b",
    r"\bits?\b",
    r"\bthis fund\b",
    r"\bthat fund\b",
    r"\bthe same fund\b",
)

SCHEME_ATTRIBUTE_PATTERNS = (
    r"\bexpense ratio\b",
    r"\bexit load\b",
    r"\bminimum sip\b",
    r"\bmin(?:imum)?\.?\s+(?:sip|investment)\b",
    r"\block[- ]?in\b",
    r"\briskometer\b",
    r"\brisk level\b",
    r"\bbenchmark\b",
    r"\bfund size\b",
    r"\b(?:assets under management|aum)\b",
    r"\bnav\b",
    r"\bminimum (?:lumpsum|lump sum)\b",
    r"\bplan type\b",
    r"\bfund manager\b",
    r"\bcategory\b",
)


def build_effective_query(
    query: str,
    recent_messages: list[StoredMessage],
) -> tuple[str, dict | None]:
    """Use thread history only for scheme context on follow-up questions."""
    cleaned = query.strip()
    filters = detect_metadata_filters(cleaned)
    if filters:
        return cleaned, filters

    scheme_name = _scheme_name_from_history(recent_messages)
    if scheme_name and _looks_like_follow_up(cleaned):
        enriched = f"{cleaned} ({scheme_name})"
        return enriched, {"scheme_name": scheme_name}

    return cleaned, None


def _looks_like_follow_up(query: str) -> bool:
    normalized = re.sub(r"\s+", " ", query.lower()).strip()
    if detect_metadata_filters(normalized):
        return False
    patterns = CONTEXT_REFERENCE_PATTERNS + SCHEME_ATTRIBUTE_PATTERNS
    return any(re.search(pattern, normalized) for pattern in patterns)


def _scheme_name_from_history(messages: list[StoredMessage]) -> str | None:
    """Return the newest scheme mentioned or resolved in this thread."""
    for message in reversed(messages):
        if message.role == "assistant":
            scheme_name = message.metadata.get("scheme_name") or message.metadata.get("source_title")
            if isinstance(scheme_name, str) and scheme_name.strip():
                return scheme_name.strip()
        else:
            filters = detect_metadata_filters(message.content)
            if filters and "scheme_name" in filters:
                return str(filters["scheme_name"])

    return None
