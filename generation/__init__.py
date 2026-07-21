"""Phase 2 — constrained answer generation."""

from generation.config import load_generation_config
from generation.generator import (
    AnswerGenerator,
    GenerationError,
    OpenAIAnswerGenerator,
    OpenAICompatibleAnswerGenerator,
    TemplateAnswerGenerator,
    build_answer_generator,
)
from generation.models import GenerationConfig

__all__ = [
    "AnswerGenerator",
    "GenerationConfig",
    "GenerationError",
    "OpenAIAnswerGenerator",
    "OpenAICompatibleAnswerGenerator",
    "TemplateAnswerGenerator",
    "build_answer_generator",
    "load_generation_config",
]
