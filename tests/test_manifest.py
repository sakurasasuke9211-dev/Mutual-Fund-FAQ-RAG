from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ingestion.manifest import ManifestError, load_manifest, validate_manifest


def test_load_manifest() -> None:
    manifest = load_manifest()
    assert manifest.amc == "HDFC Mutual Fund"
    assert len(manifest.schemes) == 5
    assert manifest.schemes[0].slug == "hdfc-mid-cap-fund-direct-growth"


def test_load_manifest_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "missing.yaml")


def test_validate_manifest_rejects_invalid_url(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad_manifest.yaml"
    manifest_path.write_text(
        yaml.dump(
            {
                "amc": "HDFC Mutual Fund",
                "source_platform": "groww.in",
                "format": "html",
                "schemes": [
                    {
                        "name": "Bad Fund",
                        "category": "equity",
                        "slug": "bad-fund",
                        "url": "https://example.com/bad-fund",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="Invalid Groww scheme URL"):
        load_manifest(manifest_path)


def test_validate_manifest_rejects_duplicate_slug(tmp_path: Path) -> None:
    manifest_path = tmp_path / "dup_manifest.yaml"
    scheme = {
        "name": "HDFC Large Cap Fund – Direct Growth",
        "category": "large-cap",
        "slug": "hdfc-large-cap-fund-direct-growth",
        "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    }
    manifest_path.write_text(
        yaml.dump(
            {
                "amc": "HDFC Mutual Fund",
                "source_platform": "groww.in",
                "format": "html",
                "schemes": [scheme, scheme],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="Duplicate scheme slug"):
        load_manifest(manifest_path)
