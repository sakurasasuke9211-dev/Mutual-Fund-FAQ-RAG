# Deployment Plan

This plan deploys the Mutual Fund FAQ RAG system across three services:

- **GitHub Actions** — scheduled corpus ingestion
- **Vercel** — React/Vite frontend
- **Koyeb** — FastAPI backend

Chroma Cloud remains the shared vector database, and Groq remains the backend LLM
provider.

## 1. Target architecture

```text
GitHub Actions scheduler
  └─ scrape → parse → chunk → embed → update Chroma Cloud
                                      ↑
                                      │
Vercel frontend ── HTTPS ──> Koyeb FastAPI backend ──> Groq API
                                      │
                                      ├─> Chroma Cloud
                                      └─> SQLite threads (ephemeral on free/eco;
                                          optional paid Volume for persistence)
```

The scheduler and backend must use the same Chroma database, collection, embedding
model, and embedding dimensions. GitHub Actions writes the latest corpus vectors;
the Koyeb backend queries those vectors without requiring a backend redeployment.

## 2. Deployment prerequisites

Create or confirm the following:

- A GitHub repository containing this project.
- A Chroma Cloud database and collection.
- A Groq API key.
- A Koyeb account for the FastAPI service.
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

### Scheduler deployment steps

1. Add the Chroma secrets to GitHub.
2. Push the workflow to the production branch.
3. Run **Actions → Daily Corpus Ingestion → Run workflow** manually.
4. Confirm that all four phases complete: scrape, parse, chunk, embed/index.
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

## 4. Koyeb backend

### Why Koyeb

Koyeb replaces Render for the FastAPI backend to avoid paid instance + disk cost
for the portfolio deployment. Prefer a free/eco web service for the API. Persistent
Volumes on Koyeb require a paid standard/GPU instance, so free-tier thread storage
is ephemeral across redeploys unless you later attach a Volume.

### Repository deploy artifacts

| File | Purpose |
|------|---------|
| `Dockerfile` | Preferred production build for FastAPI + embedding dependencies |
| `.dockerignore` | Keeps the image free of UI, tests, docs, and local data |
| `runtime.txt` | Pins Python 3.11.11 for buildpack-based deploys |
| `Procfile` | Default web process for buildpack runtimes |

### Service configuration

Create a Koyeb **Web Service** from the GitHub repository:

```text
Deployment method: GitHub
Repository: sakurasasuke9211-dev/Mutual-Fund-FAQ-RAG
Branch: main
Builder: Dockerfile (preferred) or Buildpack
Instance: free / eco Nano (or larger if the embedding model OOMs)
Regions: choose one close to users (for example fra or was)
Port: 8000 (or $PORT provided by Koyeb)
Health check: HTTP GET /health
Min instances: 1 (or scale-to-zero if you accept cold starts)
```

If using Buildpack instead of Docker, override the run command to:

```text
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Koyeb should auto-deploy when commits land on `main` after the GitHub app is
connected.

### Required Koyeb environment variables / secrets

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
THREAD_DB_PATH=/tmp/threads.db

CORS_ALLOWED_ORIGINS=https://<production-frontend-domain>
```

Store API keys and Chroma credentials as Koyeb secrets. Do not commit them.

### SQLite persistence on Koyeb

Default free/eco deployment:

```text
THREAD_DB_PATH=/tmp/threads.db
```

`/tmp` is writable but not durable across redeploys or new instances. Thread
history may reset after a redeploy. That is acceptable for the portfolio free
tier.

Optional paid persistence later:

1. Create a Koyeb Volume in the same region as the service.
2. Attach it at `/var/data`.
3. Set `THREAD_DB_PATH=/var/data/threads.db`.
4. Keep scale fixed at one instance while using SQLite.

SQLite still limits the API to a single writer-friendly instance. Move threads to
a managed database before multi-instance scaling.

### Deploy with the Koyeb control panel

1. Sign in at [app.koyeb.com](https://app.koyeb.com).
2. Create a Web Service and connect GitHub.
3. Select this repository and the `main` branch.
4. Choose Dockerfile build (or Buildpack + run-command override).
5. Expose port `8000` / `$PORT` and set the `/health` HTTP check.
6. Add the environment variables and secrets listed above.
7. Deploy and copy the public `*.koyeb.app` URL.

### Deploy with the Koyeb CLI (optional)

```powershell
koyeb login
koyeb app init fundfacts-api `
  --git github.com/sakurasasuke9211-dev/Mutual-Fund-FAQ-RAG `
  --git-branch main `
  --dockerfile Dockerfile `
  --port 8000:http `
  --checks 8000:http:/health `
  --env VECTOR_STORE_PROVIDER=chroma_cloud `
  --env CHROMA_COLLECTION_NAME=mutual_fund_faq_chunks `
  --env EMBEDDING_PROVIDER=sentence_transformers `
  --env EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 `
  --env EMBEDDING_DIMENSIONS=384 `
  --env LLM_PROVIDER=groq `
  --env LLM_MODEL=llama-3.3-70b-versatile `
  --env THREAD_STORE=sqlite `
  --env THREAD_DB_PATH=/tmp/threads.db `
  --env CORS_ALLOWED_ORIGINS=http://localhost:5173 `
  --env CHROMA_API_KEY={{ secrets.CHROMA_API_KEY }} `
  --env CHROMA_TENANT={{ secrets.CHROMA_TENANT }} `
  --env CHROMA_DATABASE={{ secrets.CHROMA_DATABASE }} `
  --env GROQ_API_KEY={{ secrets.GROQ_API_KEY }}
```

Create the referenced secrets in the Koyeb control panel before running the
command, or substitute direct `--env KEY=value` values only in a secure local
shell that never commits them.

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
VITE_API_BASE_URL=https://<koyeb-backend-domain>
```

Set it for the Production environment. Add the equivalent value to Preview only if
preview deployments are intentionally allowed to use the production backend.

Never expose Groq or Chroma credentials through a `VITE_` variable; Vite embeds
those values in browser JavaScript.

### CORS coordination

After Vercel assigns the production URL:

1. Set the Koyeb `CORS_ALLOWED_ORIGINS` value to that exact HTTPS origin.
2. Do not include a trailing slash.
3. Redeploy or restart the Koyeb backend service.
4. Redeploy Vercel if the Koyeb backend URL changed.

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
4. Deploy the Koyeb backend.
5. Verify the Koyeb `/health` endpoint.
6. Decide whether free/ephemeral SQLite is acceptable or attach a paid Volume.
7. Deploy the Vercel frontend with the Koyeb API URL.
8. Add the final Vercel origin to Koyeb CORS.
9. Redeploy Koyeb.
10. Run production smoke tests.
11. Enable or retain the daily GitHub Actions schedule.

This order ensures the backend has indexed data before the first user request and
prevents the frontend from being deployed against an unavailable API.

## 7. Production verification

### Backend checks

```powershell
curl.exe https://<koyeb-backend-domain>/health
curl.exe -X POST https://<koyeb-backend-domain>/threads
```

Expected health response:

```json
{"status":"ok"}
```

Confirm that:

- the application starts without falling back to the template generator;
- Chroma retrieval returns current source chunks;
- Groq generation succeeds;
- unknown thread IDs return the expected API error;
- logs do not expose API keys;
- on free/eco, a redeploy may clear SQLite thread history.

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
- **Koyeb** — health checks, build failures, memory use, request errors, and
  cold starts / scale-to-zero behavior.
- **Vercel** — build failures and frontend deployment status.
- **Chroma Cloud** — collection availability and record counts.
- **Groq** — request errors, rate limits, and usage.

Recommended alerts:

- GitHub Actions scheduled workflow failure.
- Koyeb health check failure.
- Koyeb restart loop, OOM, or high error rate.
- Groq or Chroma authentication/rate-limit errors.
- Unexpected zero-vector or zero-document ingestion result.

If scale-to-zero is enabled, the first API request after idle time can be slow.
Handle reconnecting state in the frontend or keep at least one warm instance for
better demo reliability.

## 9. Rollback strategy

### Frontend

Use Vercel's deployment history to promote the previous successful deployment.

### Backend

Use Koyeb's deployment history or redeploy the previous known-good Git commit.
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
- [ ] Koyeb backend service created from this repository.
- [ ] Koyeb production environment variables / secrets configured.
- [ ] Free/ephemeral SQLite accepted, or paid Volume mounted for durability.
- [ ] Backend `/health` check passing.
- [ ] Vercel project configured with `ui` as its root.
- [ ] `VITE_API_BASE_URL` points to the Koyeb HTTPS URL.
- [ ] Koyeb CORS includes the exact Vercel production origin.
- [ ] End-to-end factual and refusal queries verified.
- [ ] Scheduler failure artifacts verified.
- [ ] Monitoring ownership and rollback responsibility assigned.
