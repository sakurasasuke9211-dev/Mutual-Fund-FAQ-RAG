from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import APIConfig, load_api_config
from app.services.thread_manager import ThreadManager
from rag.pipeline import RAGPipeline, build_rag_pipeline


def get_api_config() -> APIConfig:
    return load_api_config()


def get_thread_manager(request: Request) -> ThreadManager:
    return request.app.state.thread_manager


def get_pipeline(request: Request) -> RAGPipeline:
    return request.app.state.pipeline


PipelineDep = Annotated[RAGPipeline, Depends(get_pipeline)]
ThreadManagerDep = Annotated[ThreadManager, Depends(get_thread_manager)]
APIConfigDep = Annotated[APIConfig, Depends(get_api_config)]
