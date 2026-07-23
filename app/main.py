from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_api_config
from app.routers import chat, threads
from app.services.thread_manager import build_thread_manager
from ingestion.config import load_env_file
from rag.pipeline import build_rag_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_env_file()
    if getattr(app.state, "thread_manager", None) is None:
        app.state.thread_manager = build_thread_manager()
    if getattr(app.state, "pipeline", None) is None:
        try:
            app.state.pipeline = build_rag_pipeline(guardrails_enabled=True)
            app.state.pipeline.warm()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize RAG pipeline: {exc}. "
                "Check .env (Chroma + GROQ_API_KEY / OPENAI_API_KEY / LLM_PROVIDER)."
            ) from exc
    yield


def create_app() -> FastAPI:
    api_config = load_api_config()
    app = FastAPI(title=api_config.title, version=api_config.version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(api_config.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    app.include_router(threads.router)
    app.include_router(chat.router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
