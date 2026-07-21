from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path

import yaml

from ingestion.config import CONFIG_DIR
from ingestion.models import Chunk, EmbeddingConfig, EmbedResult

logger = logging.getLogger("ingestion.embedder")

EMBEDDING_CONFIG_PATH = CONFIG_DIR / "embedding.yaml"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIMENSIONS = 384


def load_embedding_config(config_path: Path | None = None) -> EmbeddingConfig:
    path = config_path or EMBEDDING_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle).get("embedding", {})

    provider = os.getenv("EMBEDDING_PROVIDER", data.get("provider", "sentence_transformers"))
    model = os.getenv("EMBEDDING_MODEL", data.get("model", DEFAULT_MODEL))

    return EmbeddingConfig(
        provider=provider,
        model=model,
        dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", data.get("dimensions", DEFAULT_DIMENSIONS))),
        batch_size=int(data.get("batch_size", 32)),
        normalize=bool(data.get("normalize", True)),
        max_retries=int(data.get("max_retries", 3)),
        retry_delay_seconds=int(data.get("retry_delay_seconds", 2)),
        query_prefix=os.getenv("EMBEDDING_QUERY_PREFIX", data.get("query_prefix", "")),
    )


def preprocess_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    return cleaned.encode("utf-8", errors="ignore").decode("utf-8")


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Local embeddings via sentence-transformers (BGE, E5, etc.)."""

    def __init__(self, model: str, dimensions: int, max_retries: int, retry_delay_seconds: int) -> None:
        self.model_name = model
        self.dimensions = dimensions
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self._model = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                embeddings = model.encode(
                    texts,
                    batch_size=min(len(texts), 32),
                    normalize_embeddings=False,
                    show_progress_bar=False,
                )
                vectors = [vector.tolist() for vector in embeddings]
                if len(vectors) != len(texts):
                    raise RuntimeError("sentence-transformers returned unexpected embedding count")
                if any(len(vector) != self.dimensions for vector in vectors):
                    raise RuntimeError("sentence-transformers returned unexpected embedding dimensions")
                return vectors
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = self.retry_delay_seconds * attempt
                    logger.warning(
                        "Embedding attempt %s/%s failed: %s. Retrying in %ss",
                        attempt,
                        self.max_retries,
                        exc,
                        delay,
                    )
                    time.sleep(delay)

        raise RuntimeError("Embedding failed after retries") from last_error

    def _get_model(self):
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers package is required for local embeddings"
            ) from exc

        logger.info("Loading embedding model: %s", self.model_name)
        self._model = SentenceTransformer(self.model_name)

        probe = self._model.encode(["dimension probe"], normalize_embeddings=False)
        actual_dimensions = int(probe.shape[1])
        if actual_dimensions != self.dimensions:
            raise RuntimeError(
                f"Model {self.model_name} has {actual_dimensions} dimensions; "
                f"config expects {self.dimensions}"
            )

        return self._model


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Local deterministic embeddings for development and tests."""

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(text) for text in texts]

    def _hash_vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        counter = 0
        while len(values) < self.dimensions:
            block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for index in range(0, len(block), 4):
                chunk = block[index : index + 4]
                if len(chunk) < 4:
                    break
                integer = int.from_bytes(chunk, "big", signed=False)
                values.append((integer / 2**32) * 2 - 1)
                if len(values) >= self.dimensions:
                    break
            counter += 1
        return values[: self.dimensions]


class EmbeddingService:
    def __init__(
        self,
        config: EmbeddingConfig | None = None,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.config = config or load_embedding_config()
        self.provider = provider or self._build_provider(self.config)

    def embed_chunks(self, chunks: list[Chunk]) -> tuple[EmbedResult, dict[str, list[float]]]:
        if not chunks:
            result = EmbedResult(
                embedded_count=0,
                skipped_count=0,
                failed_chunk_ids=[],
                model=self.config.model,
                dimensions=self.config.dimensions,
            )
            return result, {}

        prepared: list[tuple[Chunk, str]] = []
        skipped_count = 0
        for chunk in chunks:
            text = preprocess_text(chunk.text)
            if not text:
                skipped_count += 1
                continue
            prepared.append((chunk, text))

        embedded_count = 0
        failed_chunk_ids: list[str] = []
        vectors_by_id: dict[str, list[float]] = {}

        for batch_start in range(0, len(prepared), self.config.batch_size):
            batch = prepared[batch_start : batch_start + self.config.batch_size]
            batch_chunks = [item[0] for item in batch]
            batch_texts = [item[1] for item in batch]

            try:
                vectors = self.provider.embed_texts(batch_texts)
            except Exception:
                logger.exception(
                    "Batch embedding failed for chunk IDs: %s",
                    [chunk.chunk_id for chunk in batch_chunks],
                )
                failed_chunk_ids.extend(chunk.chunk_id for chunk in batch_chunks)
                continue

            if self.config.normalize:
                vectors = [l2_normalize(vector) for vector in vectors]

            for chunk, vector in zip(batch_chunks, vectors, strict=True):
                vectors_by_id[chunk.chunk_id] = vector
                embedded_count += 1

        result = EmbedResult(
            embedded_count=embedded_count,
            skipped_count=skipped_count,
            failed_chunk_ids=failed_chunk_ids,
            model=self.config.model,
            dimensions=self.config.dimensions,
        )
        return result, vectors_by_id

    def embed_query(self, query: str) -> list[float]:
        text = preprocess_text(query)
        if not text:
            raise ValueError("Query is empty after preprocessing")
        if self.config.query_prefix:
            text = preprocess_text(f"{self.config.query_prefix}{text}")
        vector = self.provider.embed_texts([text])[0]
        if self.config.normalize:
            vector = l2_normalize(vector)
        return vector

    def _build_provider(self, config: EmbeddingConfig) -> EmbeddingProvider:
        if config.provider == "sentence_transformers":
            return SentenceTransformerEmbeddingProvider(
                model=config.model,
                dimensions=config.dimensions,
                max_retries=config.max_retries,
                retry_delay_seconds=config.retry_delay_seconds,
            )
        if config.provider == "local":
            return DeterministicEmbeddingProvider(dimensions=config.dimensions)
        raise ValueError(f"Unsupported embedding provider: {config.provider}")
