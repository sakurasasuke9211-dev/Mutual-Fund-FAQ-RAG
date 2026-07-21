from __future__ import annotations

import pytest

from ingestion.models import VectorStoreConfig
from ingestion.vector_store import VectorStore, VectorStoreError, load_vector_store_config


def test_load_vector_store_config_defaults(tmp_path) -> None:
    config_path = tmp_path / "vector_store.yaml"
    config_path.write_text(
        "vector_store:\n"
        "  provider: chroma_cloud\n"
        "  collection_name: mutual_fund_faq_chunks\n"
        "  cloud_host: api.trychroma.com\n"
        "  cloud_port: 443\n",
        encoding="utf-8",
    )

    config = load_vector_store_config(config_path)
    assert config.provider == "chroma_cloud"
    assert config.collection_name == "mutual_fund_faq_chunks"
    assert config.cloud_host == "api.trychroma.com"
    assert config.cloud_port == 443


def test_chroma_cloud_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CHROMA_API_KEY", raising=False)
    cloud_config = VectorStoreConfig(
        provider="chroma_cloud",
        collection_name="test_collection",
        cloud_host="api.trychroma.com",
        cloud_port=443,
    )

    with pytest.raises(VectorStoreError, match="CHROMA_API_KEY"):
        VectorStore(index_dir=tmp_path / "index", config=cloud_config)


def test_build_cloud_client_passes_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CHROMA_API_KEY", "test-key")
    monkeypatch.setenv("CHROMA_TENANT", "tenant-1")
    monkeypatch.setenv("CHROMA_DATABASE", "db-1")

    cloud_config = VectorStoreConfig(
        provider="chroma_cloud",
        collection_name="test_collection",
        cloud_host="api.trychroma.com",
        cloud_port=443,
    )
    store = VectorStore.__new__(VectorStore)
    store.config = cloud_config

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    class FakeChromadb:
        CloudClient = FakeClient

    store._build_cloud_client(FakeChromadb())
    assert captured["api_key"] == "test-key"
    assert captured["tenant"] == "tenant-1"
    assert captured["database"] == "db-1"
    assert captured["cloud_host"] == "api.trychroma.com"
    assert captured["cloud_port"] == 443
