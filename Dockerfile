# FastAPI query service for Railway (and other container hosts).
# Does not install Playwright or Streamlit — those are for ingestion / Streamlit Cloud.

FROM python:3.11-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

RUN apk add --no-cache --virtual .build-deps \
        build-base \
        libffi-dev

COPY requirements-api.txt .
RUN pip install --upgrade pip \
    && pip install --no-compile -r requirements-api.txt \
    && apk del .build-deps

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
