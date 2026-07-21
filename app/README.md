# Phase 4 — FastAPI application

# Phase 7 — SQLite thread persistence (§7)



HTTP API for multi-thread factual Q&A (wraps `rag/` + `guardrails/`).



| Module | Role |

|--------|------|

| `main.py` | FastAPI app, lifespan, `/health` |

| `routers/chat.py` | `POST /chat` |

| `routers/threads.py` | Thread CRUD + message history |

| `services/thread_manager.py` | Thread facade |

| `services/thread_store.py` | SQLite (default) or in-memory store |

| `services/context.py` | Follow-up scheme context from history |

| `schemas.py` | Pydantic request/response models |



```bash

python -m uvicorn app.main:app --reload --port 8000

```



Thread store (default SQLite):



| Env | Default |

|-----|---------|

| `THREAD_STORE` | `sqlite` |

| `THREAD_DB_PATH` | `data/threads.db` |



Use `THREAD_STORE=memory` for ephemeral single-process dev.



Requires `.env` (Chroma Cloud, `LLM_PROVIDER`, etc.) — same as `python -m rag.cli`.

