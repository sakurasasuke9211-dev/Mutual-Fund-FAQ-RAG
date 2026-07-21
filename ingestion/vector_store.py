from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import yaml

from ingestion.config import CONFIG_DIR, INDEX_DATA_DIR
from ingestion.models import Chunk, VectorStoreConfig


@dataclass(frozen=True)
class VectorSearchHit:
    chunk_id: str
    text: str
    metadata: dict[str, str | int]
    dense_score: float

logger = logging.getLogger("ingestion.vector_store")

VECTOR_STORE_CONFIG_PATH = CONFIG_DIR / "vector_store.yaml"
DEFAULT_COLLECTION_NAME = "mutual_fund_faq_chunks"


class VectorStoreError(Exception):
    """Raised when vector store operations fail."""


def load_vector_store_config(config_path: Path | None = None) -> VectorStoreConfig:
    path = config_path or VECTOR_STORE_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle).get("vector_store", {})

    return VectorStoreConfig(
        provider=os.getenv("VECTOR_STORE_PROVIDER", data.get("provider", "chroma_cloud")),
        collection_name=os.getenv(
            "CHROMA_COLLECTION_NAME",
            data.get("collection_name", DEFAULT_COLLECTION_NAME),
        ),
        cloud_host=os.getenv("CHROMA_HOST", data.get("cloud_host", "api.trychroma.com")),
        cloud_port=int(os.getenv("CHROMA_PORT", data.get("cloud_port", 443))),
    )


class VectorStore:
    """Chroma Cloud (default) or local persistent Chroma for chunk embeddings."""

    def __init__(
        self,
        index_dir: Path | None = None,
        config: VectorStoreConfig | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.config = config or load_vector_store_config()
        self.index_dir = Path(os.getenv("INDEX_MANIFEST_DIR", str(index_dir or INDEX_DATA_DIR)))
        self.manifest_path = self.index_dir / "manifest.json"
        self.collection_name = collection_name or self.config.collection_name
        self.persist_dir = self.index_dir / "chroma"
        self._collection = self._get_collection()

    @property
    def provider(self) -> str:
        return self.config.provider

    def delete_by_document_id(self, document_id: str) -> None:
        try:
            self._collection.delete(where={"document_id": document_id})
        except Exception as exc:
            raise VectorStoreError(f"Failed to delete vectors for document {document_id}") from exc

    def upsert_chunks(self, chunks: list[Chunk], vectors_by_id: dict[str, list[float]]) -> int:
        if not chunks:
            return 0

        ids: list[str] = []
        embeddings: list[list[float]] = []
        documents: list[str] = []
        metadatas: list[dict[str, str | int]] = []

        for chunk in chunks:
            vector = vectors_by_id.get(chunk.chunk_id)
            if vector is None:
                continue
            ids.append(chunk.chunk_id)
            embeddings.append(vector)
            documents.append(chunk.text)
            metadatas.append(self._metadata_to_store(chunk))

        if not ids:
            return 0

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        except Exception as exc:
            raise VectorStoreError("Failed to upsert chunk vectors") from exc

        return len(ids)

    def count(self) -> int:
        return self._collection.count()

    def search(
        self,
        query_embedding: list[float],
        *,
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[VectorSearchHit]:
        kwargs: dict[str, object] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            result = self._collection.query(**kwargs)
        except Exception as exc:
            raise VectorStoreError("Vector search failed") from exc

        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[VectorSearchHit] = []
        for chunk_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            if not chunk_id or document is None or metadata is None or distance is None:
                continue
            hits.append(
                VectorSearchHit(
                    chunk_id=str(chunk_id),
                    text=str(document),
                    metadata={key: value for key, value in metadata.items() if isinstance(value, (str, int))},
                    dense_score=self._distance_to_similarity(float(distance)),
                )
            )
        return hits

    def list_all(self) -> list[VectorSearchHit]:
        try:
            result = self._collection.get(include=["documents", "metadatas"])
        except Exception as exc:
            raise VectorStoreError("Failed to list indexed vectors") from exc

        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []

        records: list[VectorSearchHit] = []
        for chunk_id, document, metadata in zip(ids, documents, metadatas, strict=True):
            if not chunk_id or document is None or metadata is None:
                continue
            records.append(
                VectorSearchHit(
                    chunk_id=str(chunk_id),
                    text=str(document),
                    metadata={key: value for key, value in metadata.items() if isinstance(value, (str, int))},
                    dense_score=0.0,
                )
            )
        return records

    @staticmethod
    def _distance_to_similarity(distance: float) -> float:
        if distance <= 1.0:
            return max(0.0, 1.0 - distance)
        return 1.0 / (1.0 + distance)

    def update_manifest(
        self,
        *,
        embedding_model: str,
        dimensions: int,
        documents: list[dict[str, str | int]],
    ) -> None:
        payload = {
            "last_run_at": datetime.now().astimezone().isoformat(),
            "vector_store_provider": self.config.provider,
            "vector_store_collection": self.collection_name,
            "embedding_model": embedding_model,
            "dimensions": dimensions,
            "documents": documents,
            "total_chunks": sum(int(doc.get("chunk_count", 0)) for doc in documents),
        }
        if self.config.provider == "chroma_cloud":
            payload["chroma_cloud_host"] = self.config.cloud_host
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        with self.manifest_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _get_collection(self):
        try:
            import chromadb
        except ImportError as exc:
            raise VectorStoreError("chromadb package is required for vector storage") from exc

        if self.config.provider == "chroma_cloud":
            client = self._build_cloud_client(chromadb)
            logger.info(
                "Connected to Chroma Cloud (host=%s, collection=%s)",
                self.config.cloud_host,
                self.collection_name,
            )
        elif self.config.provider == "chroma_local":
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.persist_dir))
            logger.info("Using local Chroma at %s", self.persist_dir)
        else:
            raise VectorStoreError(f"Unsupported vector store provider: {self.config.provider}")

        return client.get_or_create_collection(name=self.collection_name)

    def _build_cloud_client(self, chromadb):
        api_key = os.getenv("CHROMA_API_KEY")
        if not api_key:
            raise VectorStoreError(
                "CHROMA_API_KEY is required for chroma_cloud provider. "
                "Set VECTOR_STORE_PROVIDER=chroma_local for offline dev/tests."
            )

        tenant = os.getenv("CHROMA_TENANT")
        database = os.getenv("CHROMA_DATABASE")

        kwargs: dict[str, object] = {
            "api_key": api_key,
            "cloud_host": self.config.cloud_host,
            "cloud_port": self.config.cloud_port,
        }
        if tenant:
            kwargs["tenant"] = tenant
        if database:
            kwargs["database"] = database

        try:
            return chromadb.CloudClient(**kwargs)
        except Exception as exc:
            raise VectorStoreError("Failed to connect to Chroma Cloud") from exc

    @staticmethod
    def _metadata_to_store(chunk: Chunk) -> dict[str, str | int]:
        metadata = asdict(chunk.metadata)
        metadata["document_id"] = chunk.document_id
        metadata["chunk_index"] = chunk.chunk_index
        metadata["token_count"] = int(chunk.token_count)
        return {key: value for key, value in metadata.items() if isinstance(value, (str, int))}
