from __future__ import annotations

from pathlib import Path

from generation.config import load_generation_config
from rag.models import RAGConfig
from retrieval.config import load_retrieval_config


def load_rag_config(config_path: Path | None = None) -> RAGConfig:
    return RAGConfig(
        retrieval=load_retrieval_config(config_path),
        generation=load_generation_config(config_path),
    )
