from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from citation.models import Citation
from generation.models import GenerationConfig
from retrieval.models import RetrievedChunk

logger = logging.getLogger("generation.generator")

SYSTEM_PROMPT = """You are a facts-only mutual fund FAQ assistant.
Answer ONLY using the provided context chunks.
Rules:
- Maximum {max_sentences} sentences.
- No investment advice, opinions, or recommendations.
- No performance comparisons or return predictions.
- If the context is insufficient, say you cannot answer from indexed sources.
- Do not invent numbers or facts not present in the context.
- Do not include URLs in the answer text.
"""


class GenerationError(Exception):
    """Raised when answer generation fails."""


class AnswerGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        citation: Citation,
    ) -> str:
        raise NotImplementedError


class TemplateAnswerGenerator(AnswerGenerator):
    """Deterministic generator for tests and offline development."""

    def __init__(self, config: GenerationConfig) -> None:
        self.config = config

    def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        citation: Citation,
    ) -> str:
        if not chunks:
            raise GenerationError("Cannot generate an answer without retrieved chunks")

        top = chunks[0]
        if str(top.metadata.get("answer_mode", "factual")) == "link_only":
            return (
                "Historical returns and NAV trends are available on the official Groww "
                "scheme page for this fund."
            )

        fact_line = self._extract_relevant_line(top.text, query)
        scheme_name = str(top.metadata.get("scheme_name", "the scheme"))
        if fact_line:
            return f"For {scheme_name}, {fact_line}."
        return (
            f"I found relevant indexed information for {scheme_name}, "
            "but could not extract a precise fact from the retrieved context."
        )

    def _extract_relevant_line(self, chunk_text: str, query: str) -> str:
        query_tokens = {token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2}
        best_line = ""
        best_score = 0

        for line in chunk_text.splitlines():
            stripped = line.strip()
            if not stripped or ":" not in stripped:
                continue
            label, value = stripped.split(":", 1)
            label_tokens = set(re.findall(r"[a-z0-9]+", label.lower()))
            score = len(query_tokens & label_tokens)
            if score > best_score:
                best_score = score
                best_line = f"{label.strip()} is {value.strip()}"

        if best_line:
            return best_line

        for line in chunk_text.splitlines():
            stripped = line.strip()
            if ":" in stripped and not stripped.lower().startswith("scheme:"):
                label, value = stripped.split(":", 1)
                return f"{label.strip()} is {value.strip()}"
        return ""


class OpenAICompatibleAnswerGenerator(AnswerGenerator):
    """Generate answers via any OpenAI-compatible Chat Completions API (OpenAI, Groq, …)."""

    def __init__(self, config: GenerationConfig, api_key: str, *, base_url: str) -> None:
        self.config = config
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.provider_label = config.provider

    def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        citation: Citation,
    ) -> str:
        if not chunks:
            raise GenerationError("Cannot generate an answer without retrieved chunks")

        if str(chunks[0].metadata.get("answer_mode", "factual")) == "link_only":
            return (
                "Historical returns and NAV trends are available on the official Groww "
                "scheme page for this fund."
            )

        import httpx

        system_prompt = SYSTEM_PROMPT.format(max_sentences=self.config.max_sentences)
        user_prompt = self._build_user_prompt(query, chunks)

        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
        except Exception as exc:
            raise GenerationError(f"{self.provider_label} generation request failed") from exc

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GenerationError(
                f"{self.provider_label} response did not contain message content"
            ) from exc

        answer = str(content).strip()
        if not answer:
            raise GenerationError(f"{self.provider_label} returned an empty answer")
        return self._enforce_sentence_limit(answer)

    def _build_user_prompt(self, query: str, chunks: list[RetrievedChunk]) -> str:
        blocks: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            blocks.append(
                "\n".join(
                    [
                        f"[CHUNK {index}]",
                        f"Source: {chunk.metadata.get('source_url', '')}",
                        f"Scheme: {chunk.metadata.get('scheme_name', '')}",
                        f"Document: {chunk.metadata.get('document_type', '')}",
                        f"Last fetched: {chunk.metadata.get('last_fetched_at', '')}",
                        f"Content: {chunk.text}",
                        "---",
                    ]
                )
            )
        context = "\n".join(blocks)
        return f"Question: {query}\n\nContext:\n{context}\n\nWrite the answer now."

    def _enforce_sentence_limit(self, answer: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
        sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
        if len(sentences) <= self.config.max_sentences:
            return answer.strip()
        return " ".join(sentences[: self.config.max_sentences])


# Backward-compatible alias
OpenAIAnswerGenerator = OpenAICompatibleAnswerGenerator


def build_answer_generator(config: GenerationConfig) -> AnswerGenerator:
    from generation.config import PROVIDER_DEFAULTS

    if config.provider == "template":
        return TemplateAnswerGenerator(config)

    defaults = PROVIDER_DEFAULTS.get(config.provider)
    if defaults is None:
        raise GenerationError(f"Unsupported LLM provider: {config.provider}")

    import os

    api_key_env = defaults["api_key_env"]
    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        logger.warning(
            "%s is not set; falling back to template generator. "
            "Set %s or LLM_PROVIDER=template in .env.",
            api_key_env,
            api_key_env,
        )
        return TemplateAnswerGenerator(config)

    base_url = config.base_url or defaults["base_url"]
    return OpenAICompatibleAnswerGenerator(config, api_key, base_url=base_url)
