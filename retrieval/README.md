# retrieval/

Hybrid search over the Chroma index written by `ingestion/`.

| Module | Role |
|--------|------|
| `dense_retriever.py` | BGE query embed + Chroma dense search |
| `filters.py` | Scheme/category metadata filters from query text |
| `bm25.py` | Sparse BM25 leg |
| `reranker.py` | Cross-encoder reranker |
| `hybrid_retriever.py` | Fuses dense + BM25 + rerank (main entry point) |

Config: `config/rag.yaml` → `retrieval.*` (loaded via `retrieval/config.py`).
