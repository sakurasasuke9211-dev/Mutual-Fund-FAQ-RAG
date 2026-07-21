# Phase 3 — query/response guardrails and refusal handling

| Module | Role |
|--------|------|
| `query_classifier.py` | Pre-retrieval PII, advisory, comparison, performance-opinion checks |
| `response_validator.py` | Post-generation sentence limit, advisory language, citation checks |
| `refusal.py` | Refusal templates + AMFI/SEBI educational links from manifest |

Config: `config/guardrails.yaml`

Integrated in `rag/pipeline.py` via `answer_guarded()`.
