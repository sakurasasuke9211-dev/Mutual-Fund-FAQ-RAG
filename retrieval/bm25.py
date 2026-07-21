from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from ingestion.vector_store import VectorSearchHit


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return {key: 1.0 for key in scores}
    return {key: (value - minimum) / (maximum - minimum) for key, value in scores.items()}


def bm25_search(
    query: str,
    records: list[VectorSearchHit],
    *,
    top_k: int,
) -> dict[str, float]:
    if not records:
        return {}

    tokenized_corpus = [tokenize(record.text) for record in records]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = tokenize(query)
    raw_scores = bm25.get_scores(query_tokens)

    ranked_indices = sorted(
        range(len(records)),
        key=lambda index: float(raw_scores[index]),
        reverse=True,
    )[:top_k]

    return {
        records[index].chunk_id: float(raw_scores[index])
        for index in ranked_indices
        if float(raw_scores[index]) > 0
    }
