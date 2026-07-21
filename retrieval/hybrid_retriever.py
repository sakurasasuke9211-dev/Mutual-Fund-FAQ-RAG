from __future__ import annotations

from ingestion.embedder import EmbeddingService
from ingestion.manifest import load_manifest
from ingestion.models import CorpusManifest
from ingestion.vector_store import VectorSearchHit, VectorStore
from retrieval.bm25 import bm25_search, normalize_scores
from retrieval.dense_retriever import DenseRetriever
from retrieval.errors import LowConfidenceRetrieval
from retrieval.filters import detect_metadata_filters, matches_metadata_filters
from retrieval.models import RetrievedChunk, RetrievalConfig
from retrieval.reranker import Reranker, build_reranker


class HybridRetriever:
    """Hybrid dense + BM25 retrieval with optional cross-encoder reranking."""

    def __init__(
        self,
        *,
        config: RetrievalConfig,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        manifest: CorpusManifest | None = None,
        dense_retriever: DenseRetriever | None = None,
        reranker: Reranker | None = None,
        corpus_records: list[VectorSearchHit] | None = None,
    ) -> None:
        self.config = config
        self.vector_store = vector_store
        self.manifest = manifest or load_manifest()
        self.dense_retriever = dense_retriever or DenseRetriever(
            config=config,
            embedding_service=embedding_service,
            vector_store=vector_store,
            manifest=self.manifest,
        )
        self.reranker = reranker or build_reranker(
            enabled=config.reranker_enabled,
            model_name=config.reranker_model,
        )
        self._corpus_records = corpus_records

    def retrieve(self, query: str, metadata_filters: dict | None = None) -> list[RetrievedChunk]:
        filters = (
            metadata_filters
            if metadata_filters is not None
            else detect_metadata_filters(query, self.manifest)
        )
        dense_hits = self.dense_retriever.search(query, filters)
        sparse_scores = self._bm25_search(query, filters)
        merged = self._fuse_hybrid_scores(dense_hits, sparse_scores)
        reranked = self.reranker.rerank(query, merged)

        top_chunks = reranked[: self.config.final_top_k]
        if not top_chunks:
            raise LowConfidenceRetrieval("No chunks retrieved for query")

        if top_chunks[0].rerank_score < self.config.min_rerank_score:
            raise LowConfidenceRetrieval("Top retrieval score is below confidence threshold")

        return top_chunks

    def _bm25_search(self, query: str, filters: dict | None) -> dict[str, float]:
        records = self._get_corpus_records()
        if filters:
            records = [
                record for record in records if matches_metadata_filters(record.metadata, filters)
            ]
        return bm25_search(query, records, top_k=self.config.sparse_top_k)

    def _fuse_hybrid_scores(
        self,
        dense_hits: list[VectorSearchHit],
        sparse_scores: dict[str, float],
    ) -> list[RetrievedChunk]:
        dense_scores = {hit.chunk_id: hit.dense_score for hit in dense_hits}
        chunk_ids = set(dense_scores) | set(sparse_scores)
        if not chunk_ids:
            return []

        dense_norm = normalize_scores({key: dense_scores.get(key, 0.0) for key in chunk_ids})
        sparse_norm = normalize_scores({key: sparse_scores.get(key, 0.0) for key in chunk_ids})
        alpha = self.config.hybrid_alpha

        records_by_id = {hit.chunk_id: hit for hit in self._get_corpus_records()}
        for hit in dense_hits:
            records_by_id[hit.chunk_id] = hit

        fused: list[RetrievedChunk] = []
        for chunk_id in chunk_ids:
            record = records_by_id.get(chunk_id)
            if record is None:
                continue
            hybrid_score = alpha * sparse_norm.get(chunk_id, 0.0) + (1.0 - alpha) * dense_norm.get(
                chunk_id, 0.0
            )
            fused.append(
                RetrievedChunk(
                    chunk_id=record.chunk_id,
                    text=record.text,
                    metadata=record.metadata,
                    dense_score=dense_scores.get(chunk_id, 0.0),
                    bm25_score=sparse_scores.get(chunk_id, 0.0),
                    hybrid_score=hybrid_score,
                    rerank_score=0.0,
                )
            )

        fused.sort(key=lambda item: item.hybrid_score, reverse=True)
        return fused[: max(self.config.dense_top_k, self.config.sparse_top_k)]

    def _get_corpus_records(self) -> list[VectorSearchHit]:
        if self._corpus_records is not None:
            return self._corpus_records
        self._corpus_records = self.vector_store.list_all()
        return self._corpus_records
