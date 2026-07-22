# FastAPI query service for Railway (and other container hosts).
# Does not install Playwright or Streamlit — those are for ingestion / Streamlit Cloud.

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements-api.txt

COPY app ./app
COPY citation ./citation
COPY config ./config
COPY generation ./generation
COPY guardrails ./guardrails
COPY ingestion ./ingestion
COPY rag ./rag
COPY retrieval ./retrieval

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
