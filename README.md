# Mutual Fund FAQ RAG



Facts-only mutual fund FAQ assistant using RAG over Groww HDFC scheme pages.



## Project structure (by phase)



| Phase | Folder | Status |

|-------|--------|--------|

| **1 — Ingestion** | `.github/workflows/`, `config/`, `ingestion/`, `data/`, `logs/` | Implemented (scheduler, scraper, manifest, parser, chunker, embedder, indexer) |

| **2 — RAG core** | `retrieval/`, `generation/`, `citation/`, `rag/` | Implemented |

| **3 — Guardrails** | `guardrails/` | Implemented |

| **4 — API & threads** | `app/` | Implemented |
| **7 — Thread persistence** | `app/services/thread_store.py` | Implemented (SQLite) |

| **5 — UI** | `ui/` | Implemented (React + Vite, Vercel-ready) |

| **6 — Tests & eval** | `tests/` | Partial (Phases 1–4 unit + API tests) |



## Phase 1: Scheduler & scraping



### GitHub Actions scheduler



Daily ingestion runs at **9:15 AM IST** via `.github/workflows/corpus-ingestion.yml`.



Manual run: **Actions → Daily Corpus Ingestion → Run workflow**



### Local scrape + parse + chunk + embed + index run



```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
playwright install chromium

copy .env.example .env        # then edit .env with your keys
python -m ingestion.pipeline
```

**Required in `.env` for Chroma Cloud indexing:**

| Variable | Where to get it |
|----------|-----------------|
| `CHROMA_API_KEY` | [trychroma.com](https://www.trychroma.com/) → database → Connect |
| `CHROMA_TENANT` | Same Connect panel |
| `CHROMA_DATABASE` | Same Connect panel |

For offline dev without Chroma Cloud, set `VECTOR_STORE_PROVIDER=chroma_local` in `.env`.



### Scrape output



- Raw HTML: `data/raw/{scheme-slug}/{timestamp}.html`

- Normalized text: `data/raw/{scheme-slug}/{timestamp}.normalized.txt`

- Metadata: `data/raw/{scheme-slug}/latest.json`

- Parsed document: `data/parsed/{scheme-slug}/latest.json`

- Chunks: `data/chunks/{scheme-slug}/latest.json`

- Vector index: **Chroma Cloud** collection `mutual_fund_faq_chunks` + local `data/index/manifest.json`

- Fund facts: `data/facts/{scheme-slug}/latest.json`

- Job summary: `logs/ingestion/ingestion_summary_latest.json`

- Latest scheduler activity: `logs/ingestion/scheduler_run_latest.log`

- Current timestamped scheduler activity: `logs/ingestion/scheduler_run_{UTC timestamp}.log`

- Current-run activity: `logs/ingestion/ingestion.log`

After a completed scheduler run, latest-only retention removes older raw snapshots,
fact/chunk histories, retired local scheme directories, old summaries, and old run
logs. Chroma vectors for schemes removed from the corpus manifest are also deleted.
Set `INGESTION_KEEP_LATEST_ONLY=false` to retain local history for debugging or audit.



## Phase 2: RAG core (query-time)



Answers factual questions by retrieving indexed chunks from Chroma Cloud, generating a short answer, and resolving a single Groww citation.

| Package | Role |
|---------|------|
| `retrieval/` | Hybrid search + rerank |
| `generation/` | Constrained LLM answer |
| `citation/` | Source URL resolution |
| `rag/` | Pipeline + CLI |
| `guardrails/` | Query/response compliance + refusals |



```bash
# Offline / tests — no LLM key:
set LLM_PROVIDER=template
python -m rag.cli "What is the expense ratio of HDFC ELSS Tax Saver Fund?"

# Production — Groq:
set LLM_PROVIDER=groq
set GROQ_API_KEY=gsk_...
python -m rag.cli --json "What is the minimum SIP for HDFC Large Cap Fund?"
```



Requires the same Chroma Cloud credentials as Phase 1 indexing (`.env`). Config: `config/rag.yaml`, `config/guardrails.yaml`.

Guardrails are **on by default**. Use `--no-guardrails` to run the Phase 2-only path.



## Phase 4: HTTP API & threads



```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```



| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/threads` | Create conversation thread |
| `GET` | `/threads` | List threads |
| `GET` | `/threads/{id}/messages` | Message history |
| `POST` | `/chat` | Ask a question (`thread_id`, `query`) |

Example:

```bash
curl -X POST http://127.0.0.1:8000/threads
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" ^
  -d "{\"thread_id\": \"<uuid>\", \"query\": \"What is the expense ratio of HDFC ELSS?\"}"
```



Config: `config/api.yaml` (`max_context_turns` for follow-up reformulation; `thread_store` / `thread_db_path` for Phase 7 persistence).

## Phase 5: React UI

Run the API, then start the UI in a second terminal:

```powershell
cd ui
copy .env.example .env
npm install
npm run dev
```

The UI opens at `http://localhost:5173`. The production target is Vercel for the
frontend, Koyeb for the FastAPI backend, and GitHub Actions for ingestion. See the
[deployment plan](docs/deployment-plan.md) and `ui/README.md`.



## Configuration



- Scheme URLs: `config/corpus_manifest.yaml`

- Embeddings: `config/embedding.yaml`

- RAG runtime: `config/rag.yaml`

- Vector store: `config/vector_store.yaml`

- Architecture: `docs/rag-architecture.md`



## Tests



```bash

pip install -r requirements.txt

pytest tests/ -v

```



## GitHub secrets



| Secret / env | Purpose |

|--------------|---------|

| `CHROMA_API_KEY` | Chroma Cloud API key ([trychroma.com](https://www.trychroma.com/)) |

| `CHROMA_TENANT` | Chroma Cloud tenant ID |

| `CHROMA_DATABASE` | Chroma Cloud database name |

| `CHROMA_HOST` | Optional region endpoint (default `api.trychroma.com`) |

| `VECTOR_STORE_PROVIDER` | Override: `chroma_cloud` (default) or `chroma_local` |

| `INDEX_MANIFEST_DIR` | Local manifest path (default `data/index`) |

| `EMBEDDING_PROVIDER` | Override provider: `sentence_transformers` (default) or `local` |

| `EMBEDDING_MODEL` | Override model (default `BAAI/bge-small-en-v1.5`) |

| `LLM_PROVIDER` | `groq` (default), `openai`, or `template` for offline/tests |

| `LLM_MODEL` | e.g. `llama-3.3-70b-versatile` (Groq) or `gpt-4o-mini` (OpenAI) |

| `GROQ_API_KEY` | Required when `LLM_PROVIDER=groq` |

| `OPENAI_API_KEY` | Required when `LLM_PROVIDER=openai` |

