# FundFacts UI

Responsive React + TypeScript frontend for the Mutual Fund FAQ Assistant. It connects to the FastAPI backend and supports health status, persistent thread selection, message history, factual answers, citations, and compliant refusal responses.

## Run locally

Start the API from the repository root:

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

In a second terminal:

```powershell
cd ui
copy .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`.

## Configuration

```env
VITE_API_BASE_URL=http://127.0.0.1:8001
```

The value is embedded at build time. Do not put Groq, Chroma, or any other secret in the UI environment.

## Deploy to Vercel

1. Import the GitHub repository into Vercel.
2. Set the root directory to `ui` and use the Vite framework preset.
3. Use `npm ci`, `npm run build`, and the `dist` output directory.
4. Set `VITE_API_BASE_URL` to the public HTTPS URL of the Koyeb FastAPI backend, without a trailing slash.
5. Deploy the frontend.
6. On the Koyeb backend service, set:

   ```env
   CORS_ALLOWED_ORIGINS=https://your-project.vercel.app
   ```

   Replace the value with the actual frontend URL and redeploy the backend.

See [`docs/deployment-plan.md`](../docs/deployment-plan.md) for the free Streamlit
Community Cloud production path. This React UI is for local development and optional
paid FastAPI hosting; Streamlit Cloud does not expose a FastAPI base URL.

## Checks

```powershell
npm run lint
npm run build
```
