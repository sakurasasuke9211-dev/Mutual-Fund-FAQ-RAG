from __future__ import annotations

import pytest

from guardrails.config import GuardrailsConfig
from guardrails.query_classifier import QueryClassifier
from guardrails.response_validator import ResponseValidator
from citation.models import Citation


@pytest.fixture
def classifier() -> QueryClassifier:
    config = GuardrailsConfig(
        max_query_length=500,
        max_sentences=3,
        advisory_phrases=("should i invest", "recommend"),
        comparison_phrases=("which fund is better", " or the "),
        performance_opinion_phrases=("will outperform",),
    )
    return QueryClassifier(config=config)


@pytest.fixture
def validator() -> ResponseValidator:
    config = GuardrailsConfig(
        max_query_length=500,
        max_sentences=3,
        advisory_phrases=(),
        comparison_phrases=(),
        performance_opinion_phrases=(),
    )
    return ResponseValidator(config=config)


def test_query_classifier_allows_factual_question(classifier: QueryClassifier) -> None:
    result = classifier.classify("What is the expense ratio of HDFC ELSS Tax Saver Fund?")
    assert result.allowed is True
    assert result.reason == "pass"


def test_query_classifier_blocks_advisory(classifier: QueryClassifier) -> None:
    result = classifier.classify("Should I invest in HDFC ELSS or large cap fund?")
    assert result.allowed is False
    assert result.reason in {"advisory", "comparison"}


@pytest.mark.parametrize(
    "query",
    [
        "Is it good to invest in this?",
        "Is this a good investment?",
        "Is this fund safe?",
        "Can I invest in this fund?",
        "Would you invest in this?",
        "Is it worth buying?",
        "Which fund should I choose?",
        "How much should I invest in this?",
        "Is now a good time to invest?",
        "Is this suitable for my risk profile?",
        "Does this match my retirement goal?",
        "Build a portfolio for me using these funds.",
        "What percentage should I allocate to this fund?",
        "Should I switch from ELSS to the large-cap fund?",
        "Compare these funds and tell me which one to buy.",
    ],
)
def test_query_classifier_blocks_recommendation_variants(
    classifier: QueryClassifier,
    query: str,
) -> None:
    result = classifier.classify(query)
    assert result.allowed is False
    assert result.reason in {"advisory", "comparison"}


@pytest.mark.parametrize(
    "query",
    [
        "What returns can I expect?",
        "Will this fund grow next year?",
        "Will this give good returns?",
        "What is the projected return?",
        "Can this fund outperform its benchmark?",
    ],
)
def test_query_classifier_blocks_prediction_variants(
    classifier: QueryClassifier,
    query: str,
) -> None:
    result = classifier.classify(query)
    assert result.allowed is False
    assert result.reason == "performance_opinion"


@pytest.mark.parametrize(
    "query",
    [
        "What is the expense ratio?",
        "What is the minimum SIP amount?",
        "What is the riskometer level?",
        "What is the lock-in period?",
        "What does exit load mean?",
        "What is the fund benchmark?",
        "Is this fund categorized as high risk?",
        "Is this an ELSS tax-saving fund?",
    ],
)
def test_query_classifier_still_allows_factual_variants(
    classifier: QueryClassifier,
    query: str,
) -> None:
    result = classifier.classify(query)
    assert result.allowed is True
    assert result.reason == "pass"


def test_query_classifier_blocks_pii(classifier: QueryClassifier) -> None:
    result = classifier.classify("My PAN is ABCDE1234F, what is the expense ratio?")
    assert result.allowed is False
    assert result.reason == "pii"


def test_response_validator_truncates_long_answers(validator: ResponseValidator) -> None:
    citation = Citation(
        source_url="https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
        source_title="HDFC ELSS Tax Saver Fund – Direct Plan Growth",
        last_updated="2026-07-16",
    )
    answer = "One. Two. Three. Four."
    result = validator.validate(answer, citation, max_sentences=3)
    assert result.valid is True
    assert result.sanitized_answer == "One. Two. Three."


def test_response_validator_blocks_advisory_language(validator: ResponseValidator) -> None:
    citation = Citation(
        source_url="https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
        source_title="HDFC ELSS Tax Saver Fund – Direct Plan Growth",
        last_updated="2026-07-16",
    )
    result = validator.validate("You should invest in this fund today.", citation)
    assert result.valid is False
    assert result.reason == "advisory_language"


def test_response_validator_blocks_missed_recommendation_answer(
    validator: ResponseValidator,
) -> None:
    citation = Citation(
        source_url="https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
        source_title="HDFC ELSS Tax Saver Fund – Direct Plan Growth",
        last_updated="2026-07-16",
    )
    result = validator.validate(
        "The indexed source does not say whether this is good to invest in.",
        citation,
    )
    assert result.valid is False
    assert result.reason == "advisory_language"
