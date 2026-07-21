# rag/

Query-time pipeline orchestration (parallel to `ingestion/pipeline.py`).

| Module | Role |
|--------|------|
| `pipeline.py` | `RAGPipeline.answer_guarded()` — guardrails → retrieve → generate → cite |
| `cli.py` | CLI entrypoint |

```bash
python -m rag.cli "What is the expense ratio of HDFC ELSS Tax Saver Fund?"
python -m rag.cli --json "Should I invest in ELSS?"   # refusal
python -m rag.cli --no-guardrails "..."               # skip Phase 3
```

Phase 3 guardrails: `guardrails/`
