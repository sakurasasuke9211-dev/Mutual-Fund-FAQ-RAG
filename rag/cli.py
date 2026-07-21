from __future__ import annotations

import argparse
import json
import sys

from rag.pipeline import GuardrailRefusal, build_rag_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask a factual mutual fund question")
    parser.add_argument("query", nargs="+", help="Natural language question")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON instead of plain text",
    )
    parser.add_argument(
        "--no-guardrails",
        action="store_true",
        help="Disable Phase 3 guardrails (retrieval-only path)",
    )
    args = parser.parse_args(argv)
    query = " ".join(args.query).strip()

    pipeline = build_rag_pipeline(guardrails_enabled=not args.no_guardrails)

    if args.no_guardrails:
        try:
            result = pipeline._answer_unsafe(query)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            payload = {
                "query": result.query,
                "response_type": "answer",
                "answer": result.answer,
                "source_url": result.citation.source_url,
                "source_title": result.citation.source_title,
                "last_updated": result.citation.last_updated,
                "chunk_ids": result.chunk_ids,
            }
            print(json.dumps(payload, indent=2))
            return 0
        print(result.answer)
        print()
        print(f"Source: {result.citation.source_url}")
        print(f"Last updated from sources: {result.citation.last_updated}")
        return 0

    try:
        guarded = pipeline.answer_guarded(query)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "query": guarded.query,
            "response_type": guarded.response_type,
            "answer": guarded.answer,
            "source_url": guarded.source_url,
            "source_title": guarded.source_title,
            "last_updated": guarded.last_updated,
            "chunk_ids": guarded.chunk_ids or [],
            "query_reason": guarded.query_reason,
            "refusal_category": guarded.refusal_category,
            "educational_link": (
                {
                    "label": guarded.educational_link.label,
                    "url": guarded.educational_link.url,
                }
                if guarded.educational_link
                else None
            ),
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(guarded.answer)
    if guarded.response_type == "answer" and guarded.source_url:
        print()
        print(f"Source: {guarded.source_url}")
        print(f"Last updated from sources: {guarded.last_updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
