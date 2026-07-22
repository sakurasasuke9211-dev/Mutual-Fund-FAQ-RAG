# FundFacts UI

Responsive React + TypeScript frontend for local development against the FastAPI
backend. Free production hosting uses Streamlit Community Cloud instead of this UI.

## Run locally

Start the API from the repository root:

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

In a second terminal:

```powershell
cd ui
copy .env.example .env
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173`.

## Configuration

```env
VITE_API_BASE_URL=http://127.0.0.1:8001
```

Do not put Groq, Chroma, or other secrets in UI environment variables.

See [`docs/deployment-plan.md`](../docs/deployment-plan.md) for Streamlit Community
Cloud (free production) and optional Vercel + public FastAPI hosting.

Production Vercel project: root directory `ui`, env `VITE_API_BASE_URL` must point
at a public FastAPI host (not the Streamlit app URL).

## Checks

```powershell
npm.cmd run lint
npm.cmd run build
```
