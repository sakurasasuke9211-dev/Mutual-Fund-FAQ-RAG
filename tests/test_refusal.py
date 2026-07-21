from __future__ import annotations

from guardrails.query_classifier import QueryClassifier
from guardrails.refusal import RefusalHandler


def test_refusal_handler_includes_amfi_link_for_advisory() -> None:
    classifier = QueryClassifier()
    handler = RefusalHandler()
    query = "Should I invest in the ELSS fund or the large-cap fund?"

    classification = classifier.classify(query)
    assert classification.allowed is False

    response = handler.from_query_classification(query, classification)
    assert response.response_type == "refusal"
    assert response.educational_link is not None
    assert "amfiindia.com" in response.educational_link.url
    assert "investment advice" in response.answer.lower()


def test_good_to_invest_question_returns_facts_only_refusal() -> None:
    classifier = QueryClassifier()
    handler = RefusalHandler()
    query = "Is it good to invest in this?"

    classification = classifier.classify(query)
    response = handler.from_query_classification(query, classification)

    assert classification.allowed is False
    assert classification.reason == "advisory"
    assert response.response_type == "refusal"
    assert response.refusal_category == "advisory"
    assert response.source_url is None
    assert "facts-only" in response.answer.lower() or "factual questions" in response.answer.lower()


def test_refusal_handler_insufficient_sources_template() -> None:
    handler = RefusalHandler()
    response = handler.insufficient_sources("What is the benchmark of an unknown scheme?")

    assert response.response_type == "refusal"
    assert response.refusal_category == "insufficient_sources"
    assert "sufficient indexed information" in response.answer
