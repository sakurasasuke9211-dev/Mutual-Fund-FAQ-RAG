from __future__ import annotations

from dataclasses import dataclass, field

from citation.models import Citation
from generation.models import GenerationConfig
from retrieval.models import RetrievedChunk, RetrievalConfig


@dataclass(frozen=True)
class RAGConfig:
    retrieval: RetrievalConfig
    generation: GenerationConfig


@dataclass(frozen=True)
class RAGAnswer:
    query: str
    answer: str
    citation: Citation
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)
