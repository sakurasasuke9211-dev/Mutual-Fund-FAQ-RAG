from __future__ import annotations

import logging

from citation.resolver import CitationResolver
from generation.generator import AnswerGenerator, GenerationError, build_answer_generator
from guardrails.models import GuardedResponse
from guardrails.query_classifier import QueryClassifier
from guardrails.refusal import RefusalHandler
from guardrails.response_validator import ResponseValidator
from ingestion.config import load_env_file
from ingestion.embedder import EmbeddingService, load_embedding_config
from ingestion.vector_store import VectorStore, load_vector_store_config
from rag.config import load_rag_config
from rag.models import RAGAnswer, RAGConfig
from retrieval.errors import LowConfidenceRetrieval, RetrievalError
from retrieval.hybrid_retriever import HybridRetriever

logger = logging.getLogger("rag.pipeline")


class RAGPipeline:
    """Orchestrates retrieval → generation → citation."""

    def __init__(
        self,
        *,
        config: RAGConfig | None = None,
        retriever: HybridRetriever | None = None,
        generator: AnswerGenerator | None = None,
        citation_resolver: CitationResolver | None = None,
        query_classifier: QueryClassifier | None = None,
        response_validator: ResponseValidator | None = None,
        refusal_handler: RefusalHandler | None = None,
        guardrails_enabled: bool = True,
    ) -> None:
        self.config = config or load_rag_config()
        self.retriever = retriever or self._build_retriever(self.config)
        self.generator = generator or build_answer_generator(self.config.generation)
        self.citation_resolver = citation_resolver or CitationResolver()
        self.guardrails_enabled = guardrails_enabled
        self.query_classifier = query_classifier or QueryClassifier()
        self.response_validator = response_validator or ResponseValidator()
        self.refusal_handler = refusal_handler or RefusalHandler()

    def answer(self, query: str, metadata_filters: dict | None = None) -> RAGAnswer:
        if self.guardrails_enabled:
            guarded = self.answer_guarded(query, metadata_filters=metadata_filters)
            if guarded.response_type == "refusal":
                raise GuardrailRefusal(guarded)
            return RAGAnswer(
                query=guarded.query,
                answer=guarded.answer,
                citation=self._citation_from_guarded(guarded),
                chunk_ids=list(guarded.chunk_ids or []),
            )

        return self._answer_unsafe(query, metadata_filters=metadata_filters)

    def answer_guarded(
        self,
        query: str,
        metadata_filters: dict | None = None,
    ) -> GuardedResponse:
        cleaned_query = query.strip()

        classification = self.query_classifier.classify(cleaned_query)
        if not classification.allowed:
            return self.refusal_handler.from_query_classification(cleaned_query, classification)

        try:
            rag_answer = self._answer_unsafe(cleaned_query, metadata_filters=metadata_filters)
        except LowConfidenceRetrieval:
            return self.refusal_handler.insufficient_sources(cleaned_query)
        except RetrievalError:
            return self.refusal_handler.insufficient_sources(cleaned_query)
        except GenerationError as exc:
            return self.refusal_handler.response_blocked(cleaned_query, str(exc))
        except ValueError as exc:
            classification = self.query_classifier.classify(cleaned_query)
            if not classification.allowed:
                return self.refusal_handler.from_query_classification(cleaned_query, classification)
            return self.refusal_handler.response_blocked(cleaned_query, str(exc))

        validation = self.response_validator.validate(
            rag_answer.answer,
            rag_answer.citation,
            max_sentences=self.config.generation.max_sentences,
        )
        if not validation.valid:
            return self.refusal_handler.response_blocked(cleaned_query, validation.reason)

        final_answer = validation.sanitized_answer or rag_answer.answer
        return GuardedResponse(
            query=rag_answer.query,
            response_type="answer",
            answer=final_answer,
            source_url=rag_answer.citation.source_url,
            source_title=rag_answer.citation.source_title,
            last_updated=rag_answer.citation.last_updated,
            chunk_ids=rag_answer.chunk_ids,
            query_reason="pass",
        )

    def _answer_unsafe(self, query: str, metadata_filters: dict | None = None) -> RAGAnswer:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("Query must not be empty")

        chunks = self.retriever.retrieve(cleaned_query, metadata_filters=metadata_filters)
        provisional_citation = self.citation_resolver.resolve(chunks)
        answer_text = self.generator.generate(cleaned_query, chunks, provisional_citation)
        citation = self.citation_resolver.resolve(chunks, answer_text)

        return RAGAnswer(
            query=cleaned_query,
            answer=answer_text,
            citation=citation,
            retrieved_chunks=chunks,
            chunk_ids=[chunk.chunk_id for chunk in chunks],
        )

    @staticmethod
    def _citation_from_guarded(guarded: GuardedResponse):
        from citation.models import Citation

        return Citation(
            source_url=str(guarded.source_url),
            source_title=str(guarded.source_title or ""),
            last_updated=str(guarded.last_updated or ""),
        )

    @staticmethod
    def _build_retriever(config: RAGConfig) -> HybridRetriever:
        embedding_service = EmbeddingService(config=load_embedding_config())
        vector_store = VectorStore(config=load_vector_store_config())
        return HybridRetriever(
            config=config.retrieval,
            embedding_service=embedding_service,
            vector_store=vector_store,
        )


class GuardrailRefusal(Exception):
    """Raised when answer() is called but guardrails return a refusal."""

    def __init__(self, response: GuardedResponse) -> None:
        self.response = response
        super().__init__(response.answer)


def build_rag_pipeline(*, guardrails_enabled: bool = True) -> RAGPipeline:
    load_env_file()
    return RAGPipeline(guardrails_enabled=guardrails_enabled)


# Backward-compatible alias
RAGService = RAGPipeline
build_rag_service = build_rag_pipeline