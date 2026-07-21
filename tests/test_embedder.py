from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ingestion.embedder import (
    DeterministicEmbeddingProvider,
    EmbeddingConfig,
    EmbeddingService,
    l2_normalize,
    load_embedding_config,
    preprocess_text,
)
from ingestion.models import Chunk, ChunkMetadata, VectorStoreConfig
from ingestion.vector_store import VectorStore, load_vector_store_config


@pytest.fixture
def embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig(
        provider="local",
        model="deterministic-local",
        dimensions=32,
        batch_size=8,
        normalize=True,
        max_retries=1,
        retry_delay_seconds=0,
    )


@pytest.fixture
def embedder(embedding_config: EmbeddingConfig) -> EmbeddingService:
    provider = DeterministicEmbeddingProvider(dimensions=embedding_config.dimensions)
    return EmbeddingService(config=embedding_config, provider=provider)


@pytest.fixture
def sample_chunk() -> Chunk:
    metadata = ChunkMetadata(
        source_url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        source_domain="groww.in",
        document_type="scheme_page",
        amc_name="HDFC Mutual Fund",
        scheme_name="HDFC Large Cap Fund – Direct Growth",
        scheme_category="large-cap",
        section_id="fund_details",
        section_title="Fund Details",
        answer_mode="factual",
        last_fetched_at="2026-07-17",
        content_hash="hash123",
        language="en",
        token_count=40,
    )
    return Chunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        chunk_index=0,
        text=(
            "Scheme: HDFC Large Cap Fund – Direct Growth\n"
            "Category: large-cap\n"
            "Section: Fund Details\n"
            "Source: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth\n\n"
            "NAV: ₹1,231.72\nExpense Ratio: 1.03%"
        ),
        token_count=40,
        metadata=metadata,
    )


def test_preprocess_text_collapses_whitespace() -> None:
    assert preprocess_text("  hello   world  ") == "hello world"


def test_l2_normalize_unit_length() -> None:
    vector = l2_normalize([3.0, 4.0])
    assert abs(sum(value * value for value in vector) - 1.0) < 1e-6


def test_embed_chunks(embedder: EmbeddingService, sample_chunk: Chunk) -> None:
    result, vectors = embedder.embed_chunks([sample_chunk])
    assert result.embedded_count == 1
    assert len(vectors["chunk-1"]) == 32


def test_embed_query_same_dimension(embedder: EmbeddingService) -> None:
    vector = embedder.embed_query("expense ratio of HDFC Large Cap Fund")
    assert len(vector) == 32
    assert abs(sum(value * value for value in vector) - 1.0) < 0.01


def test_embed_query_and_chunk_use_same_model(embedder: EmbeddingService, sample_chunk: Chunk) -> None:
    _, chunk_vectors = embedder.embed_chunks([sample_chunk])
    query_vector = embedder.embed_query(sample_chunk.text)
    assert len(query_vector) == len(chunk_vectors["chunk-1"])


def test_embed_query_applies_query_prefix() -> None:
    config = EmbeddingConfig(
        provider="local",
        model="deterministic-local",
        dimensions=32,
        batch_size=8,
        normalize=False,
        max_retries=1,
        retry_delay_seconds=0,
        query_prefix="Represent this sentence for searching relevant passages: ",
    )
    provider = DeterministicEmbeddingProvider(dimensions=32)
    embedder = EmbeddingService(config=config, provider=provider)

    with_prefix = embedder.embed_query("expense ratio")
    without_prefix = provider.embed_texts(["expense ratio"])[0]

    assert with_prefix != without_prefix


def test_load_embedding_config_defaults(tmp_path) -> None:
    config_path = tmp_path / "embedding.yaml"
    config_path.write_text(
        "embedding:\n"
        "  provider: sentence_transformers\n"
        "  model: BAAI/bge-small-en-v1.5\n"
        "  dimensions: 384\n"
        "  query_prefix: 'prefix: '\n",
        encoding="utf-8",
    )
    config = load_embedding_config(config_path)
    assert config.provider == "sentence_transformers"
    assert config.model == "BAAI/bge-small-en-v1.5"
    assert config.dimensions == 384
    assert config.query_prefix == "prefix: "


@pytest.fixture
def vector_store_config() -> VectorStoreConfig:
    return VectorStoreConfig(
        provider="chroma_local",
        collection_name="test_mutual_fund_faq_chunks",
        cloud_host="api.trychroma.com",
        cloud_port=443,
    )


@pytest.fixture
def vector_store(tmp_path, vector_store_config: VectorStoreConfig) -> VectorStore:
    return VectorStore(index_dir=tmp_path / "index", config=vector_store_config)


def test_load_vector_store_config_from_yaml(tmp_path) -> None:
    config_path = tmp_path / "vector_store.yaml"
    config_path.write_text(
        "vector_store:\n"
        "  provider: chroma_local\n"
        "  collection_name: custom_collection\n"
        "  cloud_host: europe-west1.gcp.trychroma.com\n"
        "  cloud_port: 443\n",
        encoding="utf-8",
    )
    config = load_vector_store_config(config_path)
    assert config.provider == "chroma_local"
    assert config.collection_name == "custom_collection"
    assert config.cloud_host == "europe-west1.gcp.trychroma.com"


def test_vector_store_upsert_and_manifest(
    embedder: EmbeddingService, sample_chunk: Chunk, vector_store: VectorStore
) -> None:
    result, vectors = embedder.embed_chunks([sample_chunk])
    assert result.embedded_count == 1

    vector_store.delete_by_document_id(sample_chunk.document_id)
    upserted = vector_store.upsert_chunks([sample_chunk], vectors)
    assert upserted == 1
    assert vector_store.count() == 1

    vector_store.update_manifest(
        embedding_model=embedder.config.model,
        dimensions=embedder.config.dimensions,
        documents=[
            {
                "slug": "hdfc-large-cap-fund-direct-growth",
                "document_id": sample_chunk.document_id,
                "content_hash": "hash123",
                "chunk_count": 1,
                "last_indexed_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )
    manifest = vector_store.load_manifest()
    assert manifest["total_chunks"] == 1
    assert manifest["embedding_model"] == "deterministic-local"
    assert manifest["vector_store_provider"] == "chroma_local"
