from __future__ import annotations

import logging

from ingestion.embedder import EmbeddingService
from ingestion.manifest import load_manifest
from ingestion.models import CorpusManifest
from ingestion.vector_store import VectorSearchHit, VectorStore
from retrieval.filters import detect_metadata_filters
from retrieval.models import RetrievedChunk, RetrievalConfig

logger = logging.getLogger("retrieval.dense_retriever")


class DenseRetrievalError(Exception):
    """Raised when dense vector search fails."""


class DenseRetriever:
    """Chroma dense search with optional metadata filters."""

    def __init__(
        self,
        *,
        config: RetrievalConfig,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        manifest: CorpusManifest | None = None,
    ) -> None:
        self.config = config
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.manifest = manifest or load_manifest()

    def search(self, query: str, metadata_filters: dict | None = None) -> list[VectorSearchHit]:
        filters = (
            metadata_filters
            if metadata_filters is not None
            else detect_metadata_filters(query, self.manifest)
        )
        query_vector = self.embedding_service.embed_query(query)
        try:
            return self.vector_store.search(
                query_vector,
                n_results=self.config.dense_top_k,
                where=filters,
            )
        except Exception as exc:
            raise DenseRetrievalError("Dense vector search failed") from exc

    def retrieve(self, query: str, metadata_filters: dict | None = None) -> list[RetrievedChunk]:
        hits = self.search(query, metadata_filters)
        return [
            RetrievedChunk(
                chunk_id=hit.chunk_id,
                text=hit.text,
                metadata=hit.metadata,
                dense_score=hit.dense_score,
                bm25_score=0.0,
                hybrid_score=hit.dense_score,
                rerank_score=0.0,
            )
            for hit in hits
        ]
