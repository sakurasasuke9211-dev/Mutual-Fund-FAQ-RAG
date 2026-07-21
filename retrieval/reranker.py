from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from retrieval.errors import RetrievalError
from retrieval.models import RetrievedChunk

logger = logging.getLogger("retrieval.reranker")


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        raise NotImplementedError


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not hits:
            return []

        model = self._get_model()
        pairs = [(query, hit.text) for hit in hits]
        scores = model.predict(pairs)

        reranked: list[RetrievedChunk] = []
        for hit, score in sorted(
            zip(hits, scores, strict=True),
            key=lambda item: float(item[1]),
            reverse=True,
        ):
            reranked.append(
                RetrievedChunk(
                    chunk_id=hit.chunk_id,
                    text=hit.text,
                    metadata=hit.metadata,
                    dense_score=hit.dense_score,
                    bm25_score=hit.bm25_score,
                    hybrid_score=hit.hybrid_score,
                    rerank_score=float(score),
                )
            )
        return reranked

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RetrievalError("sentence-transformers is required for reranking") from exc

        logger.info("Loading reranker model: %s", self.model_name)
        self._model = CrossEncoder(self.model_name)
        return self._model


class PassthroughReranker(Reranker):
    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=hit.chunk_id,
                text=hit.text,
                metadata=hit.metadata,
                dense_score=hit.dense_score,
                bm25_score=hit.bm25_score,
                hybrid_score=hit.hybrid_score,
                rerank_score=hit.hybrid_score,
            )
            for hit in hits
        ]


def build_reranker(*, enabled: bool, model_name: str) -> Reranker:
    if enabled:
        return CrossEncoderReranker(model_name)
    return PassthroughReranker()
