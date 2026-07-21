# Deployment Plan

This plan deploys the Mutual Fund FAQ RAG system across three services:

- **GitHub Actions** — scheduled corpus ingestion
- **Vercel** — React/Vite frontend
- **Render** — FastAPI backend

Chroma Cloud remains the shared vector database, and Groq remains the backend LLM
provider.

## 1. Target architecture

```text
GitHub Actions scheduler
  └─ scrape → parse → chunk → embed → update Chroma Cloud
                                      ↑
                                      │
Vercel frontend ── HTTPS ──> Render FastAPI backend ──> Groq API
                                      │
                                      ├─> Chroma Cloud
                                      └─> Render persistent disk (SQLite threads)
```

The scheduler and backend must use the same Chroma database, collection, embedding
model, and embedding dimensions. GitHub Actions writes the latest corpus vectors;
the Render backend queries those vectors without requiring a backend redeployment.

## 2. Deployment prerequisites

Create or confirm the following:

- A GitHub repository containing this project.
- A Chroma Cloud database and collection.
- A Groq API key.
- A Render account for the FastAPI service.
- A Vercel account for the React frontend.
- A stable production frontend domain. A custom domain is recommended because
  FastAPI CORS currently accepts exact origins rather than wildcard Vercel preview
  URLs.

Use separate production credentials from local development credentials where
possible.

## 3. GitHub Actions scheduler

### Existing workflow

The scheduler is already defined in:

```text
.github/workflows/corpus-ingestion.yml
```

It runs daily at **03:45 UTC / 09:15 IST** and supports manual
`workflow_dispatch`.

### Required GitHub Actions secrets

Configure these under **GitHub repository → Settings → Secrets and variables →
Actions**:

```text
CHROMA_API_KEY
CHROMA_TENANT
CHROMA_DATABASE
```

The ingestion job does not require the Groq key because generation occurs in the
backend, not during indexing.

### Required scheduler environment

Keep these values aligned with the backend:

```text
VECTOR_STORE_PROVIDER=chroma_cloud
CHROMA_COLLECTION_NAME=mutual_fund_faq_chunks
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSIONS=384
INGESTION_KEEP_LATEST_ONLY=true
```

The repository configuration already provides these defaults, but explicitly
setting critical production values in the workflow reduces configuration drift.

### Scheduler deployment steps

1. Add the Chroma secrets to GitHub.
2. Push the workflow to the production branch.
3. Run **Actions → Daily Corpus Ingestion → Run workflow** manually.
4. Confirm that all four phases complete:
   - scrape
   - parse
   - chunk
   - embed/index
5. Confirm that the Chroma collection contains the expected scheme documents.
6. Download and inspect the index manifest artifact.
7. Leave the daily schedule enabled only after the manual run succeeds.

### Scheduler retention and failures

- The pipeline keeps only the newest local artifacts per component.
- GitHub-hosted runner files disappear after the job.
- Failure logs and raw snapshots are uploaded as temporary GitHub artifacts.
- A failed scheduler run must not trigger a frontend or backend deployment.
- GitHub Actions concurrency prevents two ingestion runs from modifying the
  collection simultaneously.

## 4. Render backend

### Service configuration

Create a Render **Web Service** connected to the GitHub repository:

```text
Runtime: Python
Root directory: repository root
Build command: pip install -r requirements.txt
Start command: python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health check path: /health
Production branch: main
Python version: 3.11
```

Render should auto-deploy only after changes are merged into the production branch.

### Required Render environment variables

```text
VECTOR_STORE_PROVIDER=chroma_cloud
CHROMA_API_KEY=<secret>
CHROMA_TENANT=<secret>
CHROMA_DATABASE=<secret>
CHROMA_COLLECTION_NAME=mutual_fund_faq_chunks

EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSIONS=384

LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=<secret>

THREAD_STORE=sqlite
THREAD_DB_PATH=/var/data/threads.db

CORS_ALLOWED_ORIGINS=https://<production-frontend-domain>
```

Mark API keys and Chroma credentials as secret values in Render.

### SQLite persistence

Attach a Render persistent disk:

```text
Mount path: /var/data
Database path: /var/data/threads.db
```

Without a persistent disk, thread history will be lost on restart or redeployment.
SQLite also limits this deployment to one backend instance. Do not horizontally
scale the API while it uses a single-instance SQLite file. Move threads to a managed
PostgreSQL database before multi-instance scaling.

### Current Render configuration gap

The repository's current `render.yaml` defines `fundfacts-ui` as a Render static
site. Before deployment execution, replace that service definition with the
FastAPI web service above or create the backend manually and remove the obsolete
frontend Blueprint configuration. The frontend will be hosted by Vercel.

## 5. Vercel frontend

Create a Vercel project from the same GitHub repository:

```text
Framework preset: Vite
Root directory: ui
Install command: npm ci
Build command: npm run build
Output directory: dist
Node.js version: 22
Production branch: main
```

No `vercel.json` file is required for the initial deployment because Vercel detects
Vite and serves its SPA fallback. Add one later only if explicit headers, redirects,
or rewrites are needed.

### Required Vercel environment variable

```text
VITE_API_BASE_URL=https://<render-backend-domain>
```

Set it for the Production environment. Add the equivalent value to Preview only if
preview deployments are intentionally allowed to use the production backend.

Never expose Groq or Chroma credentials through a `VITE_` variable; Vite embeds
those values in browser JavaScript.

### CORS coordination

After Vercel assigns the production URL:

1. Set the Render `CORS_ALLOWED_ORIGINS` value to that exact HTTPS origin.
2. Do not include a trailing slash.
3. Restart or redeploy the Render backend.
4. Redeploy Vercel if the Render backend URL changed.

For multiple approved frontend domains, use a comma-separated value:

```text
CORS_ALLOWED_ORIGINS=https://fundfacts.example.com,https://fundfacts.vercel.app
```

Dynamic Vercel preview origins are not automatically accepted by the current
backend. Keep previews disconnected from production or add an explicit,
security-reviewed preview-origin policy before enabling them.

## 6. Recommended deployment order

1. Provision Chroma Cloud and create production credentials.
2. Configure GitHub Actions secrets.
3. Run ingestion manually and verify the Chroma collection.
4. Deploy the Render backend.
5. Verify the Render `/health` endpoint.
6. Attach and verify the Render persistent disk.
7. Deploy the Vercel frontend with the Render API URL.
8. Add the final Vercel origin to Render CORS.
9. Redeploy Render.
10. Run production smoke tests.
11. Enable or retain the daily GitHub Actions schedule.

This order ensures the backend has indexed data before the first user request and
prevents the frontend from being deployed against an unavailable API.

## 7. Production verification

### Backend checks

```powershell
curl.exe https://<render-backend-domain>/health
curl.exe -X POST https://<render-backend-domain>/threads
```

Expected health response:

```json
{"status":"ok"}
```

Confirm that:

- the application starts without falling back to the template generator;
- Chroma retrieval returns current source chunks;
- Groq generation succeeds;
- a thread survives a Render service restart;
- unknown thread IDs return the expected API error;
- logs do not expose API keys.

### Frontend checks

Confirm that:

- the Vercel page loads over HTTPS;
- the connection indicator reports the API as connected;
- creating and switching threads works;
- factual questions return answers and citations;
- follow-up questions preserve the active scheme context;
- advisory questions display the facts-only refusal;
- browser requests show no CORS or mixed-content errors;
- desktop and mobile layouts remain usable.

### Scheduler checks

Confirm that:

- manual dispatch succeeds;
- the next scheduled execution starts at the expected UTC time;
- only one ingestion run executes at a time;
- changed content replaces prior vectors;
- schemes removed from the corpus manifest are removed from Chroma;
- failed runs upload diagnostic artifacts.

## 8. Monitoring and operations

Review these systems daily during the initial rollout:

- **GitHub Actions** — scheduler success, duration, and ingestion logs.
- **Render** — health checks, startup failures, memory use, request errors, and
  persistent disk availability.
- **Vercel** — build failures and frontend deployment status.
- **Chroma Cloud** — collection availability and record counts.
- **Groq** — request errors, rate limits, and usage.

Recommended alerts:

- GitHub Actions scheduled workflow failure.
- Render health check failure.
- Render restart loop or high error rate.
- Groq or Chroma authentication/rate-limit errors.
- Unexpected zero-vector or zero-document ingestion result.

Render free-tier cold starts, if used, can make the first API request slow. Use an
appropriate paid instance or clearly handle the initial reconnecting state in the
frontend for production reliability.

## 9. Rollback strategy

### Frontend

Use Vercel's deployment history to promote the previous successful deployment.

### Backend

Use Render's deployment history or redeploy the previous known-good Git commit.
Do not roll back environment variables unless the earlier application version
requires different values.

### Scheduler

Disable the GitHub Actions schedule if ingestion is damaging or unreliable, then
run a corrected workflow manually before re-enabling it.

### Corpus data

The latest-only retention policy intentionally does not maintain historical corpus
versions. Application code can be rolled back, but an earlier vector corpus cannot
be restored automatically. If corpus rollback becomes a production requirement,
introduce versioned Chroma collections and switch the backend collection name only
after a new collection passes validation.

## 10. Release checklist

- [ ] Production Chroma database and collection created.
- [ ] GitHub Actions Chroma secrets configured.
- [ ] Manual ingestion completed successfully.
- [ ] Chroma document and vector counts validated.
- [ ] Render backend service created.
- [ ] Render production environment variables configured.
- [ ] Render persistent disk mounted at `/var/data`.
- [ ] Backend `/health` check passing.
- [ ] Vercel project configured with `ui` as its root.
- [ ] `VITE_API_BASE_URL` points to the Render HTTPS URL.
- [ ] Render CORS includes the exact Vercel production origin.
- [ ] End-to-end factual and refusal queries verified.
- [ ] Thread persistence verified after backend restart.
- [ ] Scheduler failure artifacts verified.
- [ ] Monitoring ownership and rollback responsibility assigned.
