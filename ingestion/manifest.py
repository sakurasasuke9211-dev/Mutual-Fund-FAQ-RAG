from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

from ingestion.config import MANIFEST_PATH
from ingestion.models import CorpusManifest, RefusalLink, SchemeEntry

GROWW_MF_URL_PATTERN = re.compile(
    r"^https://groww\.in/mutual-funds/[a-z0-9-]+$"
)


class ManifestError(Exception):
    """Raised when the corpus manifest is missing or invalid."""


def load_manifest(manifest_path: Path | None = None, validate: bool = True) -> CorpusManifest:
    path = manifest_path or MANIFEST_PATH
    if not path.exists():
        raise ManifestError(f"Corpus manifest not found: {path}")

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ManifestError("Corpus manifest must be a YAML mapping.")

    schemes_raw = data.get("schemes")
    if not schemes_raw:
        raise ManifestError("Corpus manifest must define at least one scheme.")

    schemes: list[SchemeEntry] = []
    seen_slugs: set[str] = set()
    seen_urls: set[str] = set()

    for index, entry in enumerate(schemes_raw, start=1):
        required = ("name", "category", "slug", "url")
        missing = [field for field in required if not entry.get(field)]
        if missing:
            raise ManifestError(
                f"Scheme #{index} is missing required fields: {', '.join(missing)}"
            )

        scheme = SchemeEntry(
            name=str(entry["name"]),
            category=str(entry["category"]),
            slug=str(entry["slug"]),
            url=str(entry["url"]),
        )

        if scheme.slug in seen_slugs:
            raise ManifestError(f"Duplicate scheme slug: {scheme.slug}")
        if scheme.url in seen_urls:
            raise ManifestError(f"Duplicate scheme URL: {scheme.url}")

        seen_slugs.add(scheme.slug)
        seen_urls.add(scheme.url)
        schemes.append(scheme)

    refusal_links = [
        RefusalLink(label=str(item["label"]), url=str(item["url"]))
        for item in data.get("refusal_links", [])
    ]

    manifest = CorpusManifest(
        amc=str(data.get("amc", "")),
        source_platform=str(data.get("source_platform", "")),
        format=str(data.get("format", "html")),
        schemes=schemes,
        refusal_links=refusal_links,
    )

    if validate:
        validate_manifest(manifest)

    return manifest


def validate_manifest(manifest: CorpusManifest) -> None:
    if not manifest.amc:
        raise ManifestError("Manifest must define amc.")
    if manifest.format != "html":
        raise ManifestError("v1 manifest format must be html.")
    if manifest.source_platform != "groww.in":
        raise ManifestError("v1 manifest source_platform must be groww.in.")

    for scheme in manifest.schemes:
        if not GROWW_MF_URL_PATTERN.match(scheme.url):
            raise ManifestError(f"Invalid Groww scheme URL: {scheme.url}")
        if scheme.slug not in scheme.url:
            raise ManifestError(
                f"Scheme slug '{scheme.slug}' must appear in URL: {scheme.url}"
            )
        domain = urlparse(scheme.url).netloc
        if domain != "groww.in":
            raise ManifestError(f"Scheme URL must be on groww.in: {scheme.url}")


def allowed_urls(manifest: CorpusManifest) -> set[str]:
    return {scheme.url for scheme in manifest.schemes}


def get_scheme_by_slug(manifest: CorpusManifest, slug: str) -> SchemeEntry | None:
    for scheme in manifest.schemes:
        if scheme.slug == slug:
            return scheme
    return None
