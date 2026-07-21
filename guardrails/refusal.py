from __future__ import annotations

from guardrails.models import (
    EducationalLink,
    GuardedResponse,
    QueryClassification,
    QueryDecisionReason,
    RefusalCategory,
)
from ingestion.manifest import load_manifest


REFUSAL_TEMPLATE = """I can only answer factual questions about mutual fund schemes using official public sources. I cannot provide investment advice or recommendations.

{body}

For investor education, please refer to: {education_label} ({education_url})"""


class RefusalHandler:
    """Build structured refusal responses with educational links."""

    def __init__(self) -> None:
        manifest = load_manifest()
        self._default_link = (
            EducationalLink(
                label=manifest.refusal_links[0].label,
                url=manifest.refusal_links[0].url,
            )
            if manifest.refusal_links
            else EducationalLink(
                label="AMFI investor education",
                url="https://www.amfiindia.com/investor/knowledge-center",
            )
        )

    def from_query_classification(
        self,
        query: str,
        classification: QueryClassification,
    ) -> GuardedResponse:
        category = self._category_for_reason(classification.reason)
        body = self._body_for_category(category, classification.message)
        return GuardedResponse(
            query=query.strip(),
            response_type="refusal",
            answer=self._format_refusal(body),
            educational_link=self._default_link,
            query_reason=classification.reason,
            refusal_category=category,
        )

    def insufficient_sources(self, query: str) -> GuardedResponse:
        body = (
            "I could not find sufficient indexed information to answer that question "
            "from the official Groww scheme pages in the corpus."
        )
        return GuardedResponse(
            query=query.strip(),
            response_type="refusal",
            answer=self._format_refusal(body),
            educational_link=self._default_link,
            query_reason="pass",
            refusal_category="insufficient_sources",
        )

    def response_blocked(self, query: str, reason: str) -> GuardedResponse:
        body = (
            "I cannot return that generated response because it did not pass compliance checks "
            f"({reason.replace('_', ' ')})."
        )
        return GuardedResponse(
            query=query.strip(),
            response_type="refusal",
            answer=self._format_refusal(body),
            educational_link=self._default_link,
            query_reason="pass",
            refusal_category="response_blocked",
        )

    def _format_refusal(self, body: str) -> str:
        return REFUSAL_TEMPLATE.format(
            body=body.strip(),
            education_label=self._default_link.label,
            education_url=self._default_link.url,
        )

    @staticmethod
    def _category_for_reason(reason: QueryDecisionReason) -> RefusalCategory:
        mapping: dict[QueryDecisionReason, RefusalCategory] = {
            "pii": "pii",
            "advisory": "advisory",
            "comparison": "advisory",
            "performance_opinion": "performance_opinion",
            "empty": "advisory",
            "too_long": "advisory",
            "pass": "advisory",
        }
        return mapping.get(reason, "advisory")

    @staticmethod
    def _body_for_category(category: RefusalCategory, detail: str) -> str:
        if category == "pii":
            return "I cannot process queries that contain personal or account information such as PAN, phone, or email."
        if category == "performance_opinion":
            return "I cannot provide performance predictions, return forecasts, or investment opinions."
        if detail:
            return detail
        return "This question falls outside the facts-only scope of the assistant."
