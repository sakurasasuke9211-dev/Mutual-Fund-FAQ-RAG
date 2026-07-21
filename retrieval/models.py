from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalConfig:
    dense_top_k: int
    sparse_top_k: int
    hybrid_alpha: float
    final_top_k: int
    reranker_enabled: bool
    reranker_model: str
    min_rerank_score: float


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict[str, str | int]
    dense_score: float
    bm25_score: float
    hybrid_score: float
    rerank_score: float
