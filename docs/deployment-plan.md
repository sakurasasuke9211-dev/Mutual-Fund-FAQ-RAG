# Deployment Plan

This plan deploys the Mutual Fund FAQ RAG system across:

- **GitHub Actions** — scheduled corpus ingestion into Chroma Cloud
- **Streamlit Community Cloud** — free hosted query app (RAG pipeline in-process)

The React/Vite UI (`ui/`) and FastAPI app (`app/`) remain in the repository for
local development and optional paid hosting. On the free production path they are
not required.

Chroma Cloud remains the shared vector database. Groq remains the LLM provider.

## Important: Streamlit is free, but it is not a REST API host

**Streamlit Community Cloud is free** for public apps connected to a GitHub repo.

It hosts a **Streamlit web app**, not a FastAPI service. You get a public URL like:

```text
https://<app-name>.streamlit.app
```

You do **not** get endpoints such as `POST /chat` or `GET /health` from Streamlit
Cloud. The “API” for the free path is the Streamlit app itself: it loads
`RAGPipeline` in-process and answers chat turns in the browser UI.

If you later need a public REST API again, host FastAPI on a separate free or paid
compute provider and point `ui/` at that URL.

## 1. Target architecture

```text
GitHub Actions scheduler
  └─ scrape → parse → chunk → embed → update Chroma Cloud
                                      ↑
                                      │
Streamlit Community Cloud app ────────┘
  (streamlit_app.py → RAGPipeline → Groq + Chroma Cloud)
```

Local optional stack:

```text
React UI (Vite) ──> FastAPI (uvicorn) ──> Groq + Chroma Cloud
```

## 2. Deployment prerequisites

- GitHub repository with this project (already: `Mutual-Fund-FAQ-RAG`)
- Chroma Cloud database + collection populated by a successful ingestion run
- Groq API key
- Free [Streamlit Community Cloud](https://share.streamlit.io/) account (sign in with GitHub)

## 3. GitHub Actions scheduler

Unchanged from the existing workflow:

```text
.github/workflows/corpus-ingestion.yml
```

Required Actions secrets:

```text
CHROMA_API_KEY
CHROMA_TENANT
CHROMA_DATABASE
```

Keep embedding settings aligned with the Streamlit app:

```text
VECTOR_STORE_PROVIDER=chroma_cloud
CHROMA_COLLECTION_NAME=mutual_fund_faq_chunks
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSIONS=384
```

Run a successful ingestion once before expecting good Streamlit answers.

## 4. Streamlit Community Cloud (free production app)

### Repository entrypoint

| File | Purpose |
|------|---------|
| `streamlit_app.py` | Hosted chat UI + in-process RAG/guardrails |
| `.streamlit/config.toml` | Streamlit server defaults |
| `.streamlit/secrets.toml.example` | Template for Cloud secrets (do not commit real secrets) |
| `requirements.txt` | Includes `streamlit` plus existing RAG dependencies |

### Steps to deploy and get the public app URL

1. Open [https://share.streamlit.io/](https://share.streamlit.io/) and sign in with GitHub.
2. Click **New app**.
3. Select repository `sakurasasuke9211-dev/Mutual-Fund-FAQ-RAG`.
4. Branch: `main`.
5. Main file path: `streamlit_app.py`.
6. Open **Advanced settings → Secrets** and paste TOML secrets (see below).
7. Click **Deploy**.
8. After the build succeeds, copy the public URL shown in the browser / app settings:

```text
https://<your-app-name>.streamlit.app
```

That URL is the free hosted “backend + UI” for the portfolio.

### Required Streamlit secrets (TOML)

Paste into Community Cloud secrets (same format as `.streamlit/secrets.toml.example`):

```toml
VECTOR_STORE_PROVIDER = "chroma_cloud"
CHROMA_API_KEY = "ck-xxxxxxxx"
CHROMA_TENANT = "your-tenant-uuid"
CHROMA_DATABASE = "your-database-name"
CHROMA_COLLECTION_NAME = "mutual_fund_faq_chunks"

EMBEDDING_PROVIDER = "sentence_transformers"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = "384"

LLM_PROVIDER = "groq"
LLM_MODEL = "llama-3.3-70b-versatile"
GROQ_API_KEY = "gsk_xxxxxxxx"
```

Locally, copy the example file:

```powershell
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Fill real values, then run:

```powershell
python -m streamlit run streamlit_app.py
```

### Resource note

The query path loads `sentence-transformers` (BGE) and talks to Chroma Cloud + Groq.
Streamlit Community Cloud free resources are limited. If the app OOMs on first
load, reduce concurrency, reboot the app, or move the FastAPI path to a larger
free/paid host later while keeping Streamlit as a lighter demo UI.

### What you will not get from Streamlit Cloud

- No FastAPI OpenAPI docs at `/docs`
- No `POST /threads` or `POST /chat` REST contract
- No durable multi-user SQLite thread store across users (session state only)

## 5. Optional FastAPI + Vercel React UI

The free production path is Streamlit only. Deploy the React UI on Vercel only when
you also host FastAPI publicly (Streamlit does **not** expose `/health` or `/chat`).

### Local development

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

```powershell
cd ui
copy .env.example .env
npm.cmd install
npm.cmd run dev
```

### Vercel project settings

Create a Vercel project from the same GitHub repository (or deploy `ui/` via CLI):

```text
Framework preset: Vite
Root directory: ui
Install command: npm ci
Build command: npm run build
Output directory: dist
Node.js version: 22
Production branch: main
```

`ui/vercel.json` provides an SPA rewrite so deep links refresh correctly.

### Required Vercel environment variable

```text
VITE_API_BASE_URL=https://<public-fastapi-host>
```

Set it for Production. Never put Groq or Chroma credentials in `VITE_` variables.

### CORS coordination

After Vercel assigns the production URL, set on the FastAPI host:

```text
CORS_ALLOWED_ORIGINS=https://<your-project>.vercel.app
```

No trailing slash. Redeploy FastAPI after updating CORS, then redeploy Vercel if the
API base URL changed.

## 6. Recommended deployment order

1. Configure GitHub Actions Chroma secrets.
2. Run ingestion successfully.
3. Create Streamlit Community Cloud app from this repo (`streamlit_app.py`).
4. Paste Streamlit secrets.
5. Open the `*.streamlit.app` URL and smoke-test factual + refusal questions.
6. Keep the daily GitHub Actions schedule enabled.

## 7. Verification

On the Streamlit app URL:

- App loads without secret/config crash messages.
- Factual scheme questions return answers with source links.
- Follow-ups keep scheme context within the same browser session.
- Advisory questions show the facts-only refusal path.
- Chroma/Groq auth failures are visible as clear errors, not silent empty replies.

Scheduler checks remain the same as before (manual dispatch, artifacts, Chroma
counts).

## 8. Monitoring and rollback

- **GitHub Actions** — ingestion success/failure.
- **Streamlit Cloud** — reboot app, view logs, update secrets, redeploy from `main`.
- **Chroma / Groq** — vendor dashboards for auth and rate limits.

Rollback: redeploy a previous Git commit from Streamlit Cloud, or revert `main`
and let the app rebuild.

## 9. Release checklist

- [ ] Successful ingestion into production Chroma collection.
- [ ] Streamlit Community Cloud app created from `streamlit_app.py`.
- [ ] Streamlit secrets configured (Chroma + Groq + embedding settings).
- [ ] Public `*.streamlit.app` URL works over HTTPS.
- [ ] Factual and refusal smoke tests passed.
- [ ] Scheduler remains enabled after a green run.
