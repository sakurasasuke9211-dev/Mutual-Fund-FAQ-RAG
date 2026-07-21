from __future__ import annotations

import re

from ingestion.manifest import load_manifest
from ingestion.models import CorpusManifest


def detect_metadata_filters(query: str, manifest: CorpusManifest | None = None) -> dict | None:
    manifest = manifest or load_manifest()
    normalized = re.sub(r"\s+", " ", query.lower()).strip()

    for scheme in manifest.schemes:
        if scheme.name.lower() in normalized:
            return {"scheme_name": scheme.name}
        slug_phrase = scheme.slug.replace("-", " ")
        if slug_phrase in normalized:
            return {"scheme_name": scheme.name}

    category_aliases = {
        "elss": "elss",
        "tax saver": "elss",
        "large cap": "large-cap",
        "mid cap": "mid-cap",
        "focused": "focused",
        "equity fund": "equity",
    }
    for alias, category in category_aliases.items():
        if alias in normalized:
            matching = [scheme for scheme in manifest.schemes if scheme.category == category]
            if len(matching) == 1:
                return {"scheme_name": matching[0].name}
            if len(matching) > 1:
                return {"scheme_category": category}

    return None


def matches_metadata_filters(metadata: dict[str, str | int], filters: dict) -> bool:
    for key, expected in filters.items():
        if str(metadata.get(key, "")) != str(expected):
            return False
    return True
