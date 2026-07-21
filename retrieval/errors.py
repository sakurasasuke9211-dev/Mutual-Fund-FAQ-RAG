from __future__ import annotations


class RetrievalError(Exception):
    """Raised when retrieval fails."""


class LowConfidenceRetrieval(RetrievalError):
    """Raised when no chunk meets the minimum rerank threshold."""
