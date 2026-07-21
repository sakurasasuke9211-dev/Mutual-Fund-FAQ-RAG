# generation/

Constrained LLM answer synthesis from retrieved chunks.

| Module | Role |
|--------|------|
| `generator.py` | Groq / OpenAI / `template` providers; ≤3-sentence factual answers |

Config: `config/rag.yaml` → `generation.*` (loaded via `generation/config.py`).
