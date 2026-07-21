from __future__ import annotations

import os
from pathlib import Path

import yaml

from ingestion.config import CONFIG_DIR
from retrieval.models import RetrievalConfig

RAG_CONFIG_PATH = CONFIG_DIR / "rag.yaml"


def load_retrieval_config(config_path: Path | None = None) -> RetrievalConfig:
    path = config_path or RAG_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        retrieval = yaml.safe_load(handle).get("rag", {}).get("retrieval", {})

    return RetrievalConfig(
        dense_top_k=int(os.getenv("RAG_DENSE_TOP_K", retrieval.get("dense_top_k", 10))),
        sparse_top_k=int(os.getenv("RAG_SPARSE_TOP_K", retrieval.get("sparse_top_k", 10))),
        hybrid_alpha=float(os.getenv("RAG_HYBRID_ALPHA", retrieval.get("hybrid_alpha", 0.5))),
        final_top_k=int(os.getenv("RAG_FINAL_TOP_K", retrieval.get("final_top_k", 3))),
        reranker_enabled=os.getenv(
            "RAG_RERANKER_ENABLED", str(retrieval.get("reranker_enabled", True))
        ).lower()
        == "true",
        reranker_model=os.getenv(
            "RAG_RERANKER_MODEL",
            retrieval.get("reranker_model", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
        ),
        min_rerank_score=float(
            os.getenv("RAG_MIN_RERANK_SCORE", retrieval.get("min_rerank_score", -5.0))
        ),
    )
