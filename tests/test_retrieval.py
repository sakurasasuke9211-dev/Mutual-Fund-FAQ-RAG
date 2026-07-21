from __future__ import annotations

from retrieval.filters import detect_metadata_filters


def test_detect_metadata_filters_matches_scheme_name() -> None:
    filters = detect_metadata_filters("What is the expense ratio of HDFC ELSS Tax Saver Fund?")
    assert filters == {"scheme_name": "HDFC ELSS Tax Saver Fund – Direct Plan Growth"}
