from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from ingestion.config import DATA_DIR, LOGS_DIR
from ingestion.manifest import load_manifest

logger = logging.getLogger("ingestion.retention")


@dataclass(frozen=True)
class RetentionResult:
    files_removed: int = 0
    directories_removed: int = 0

    def __add__(self, other: "RetentionResult") -> "RetentionResult":
        return RetentionResult(
            files_removed=self.files_removed + other.files_removed,
            directories_removed=self.directories_removed + other.directories_removed,
        )


def prune_generated_artifacts(
    *,
    current_activity_log: Path,
    current_summary: Path,
    data_dir: Path | None = None,
    logs_dir: Path | None = None,
    active_slugs: set[str] | None = None,
) -> RetentionResult:
    """Keep only the newest usable artifact for each ingestion component.

    This runs only after the full pipeline and summary complete successfully.
    A malformed `latest.json` causes that scheme directory to be left untouched,
    favoring recoverability over aggressive deletion.
    """
    root = data_dir or DATA_DIR
    log_root = logs_dir or LOGS_DIR
    slugs = (
        active_slugs
        if active_slugs is not None
        else {scheme.slug for scheme in load_manifest().schemes}
    )

    result = RetentionResult()
    result += _prune_raw(root / "raw", slugs)
    result += _prune_latest_store(root / "parsed", slugs)
    result += _prune_latest_store(root / "facts", slugs, keep_catalog=True)
    result += _prune_latest_store(root / "chunks", slugs, keep_catalog=True)
    result += _prune_logs(
        log_root,
        current_activity_log=current_activity_log,
        current_summary=current_summary,
    )
    return result


def _prune_raw(raw_dir: Path, active_slugs: set[str]) -> RetentionResult:
    if not raw_dir.exists():
        return RetentionResult()

    result = RetentionResult()
    for child in list(raw_dir.iterdir()):
        if child.is_file():
            if child.name.startswith("_debug"):
                result += _remove_file(child)
            continue

        if child.name not in active_slugs:
            result += _remove_directory(child)
            continue

        latest_path = child / "latest.json"
        if not latest_path.exists():
            logger.warning("Retention skipped raw directory without latest.json: %s", child)
            continue

        try:
            payload = json.loads(latest_path.read_text(encoding="utf-8"))
            keep = {latest_path.resolve()}
            for key in ("raw_path", "normalized_path", "meta_path"):
                value = payload.get(key)
                if not value:
                    continue
                referenced = Path(str(value)).resolve()
                if referenced.parent == child.resolve():
                    keep.add(referenced)
        except (OSError, ValueError, TypeError):
            logger.exception("Retention skipped malformed raw latest file: %s", latest_path)
            continue

        for artifact in list(child.iterdir()):
            if artifact.is_file() and artifact.resolve() not in keep and artifact.name != ".gitkeep":
                result += _remove_file(artifact)

    return result


def _prune_latest_store(
    store_dir: Path,
    active_slugs: set[str],
    *,
    keep_catalog: bool = False,
) -> RetentionResult:
    if not store_dir.exists():
        return RetentionResult()

    result = RetentionResult()
    for child in list(store_dir.iterdir()):
        if child.is_file():
            if keep_catalog and child.name == "catalog.json":
                continue
            if child.name != ".gitkeep":
                result += _remove_file(child)
            continue

        if child.name not in active_slugs:
            result += _remove_directory(child)
            continue

        latest_path = child / "latest.json"
        if not latest_path.exists():
            logger.warning("Retention skipped store directory without latest.json: %s", child)
            continue

        for artifact in list(child.iterdir()):
            if artifact == latest_path or artifact.name == ".gitkeep":
                continue
            if artifact.is_dir():
                result += _remove_directory(artifact)
            else:
                result += _remove_file(artifact)

    return result


def _prune_logs(
    logs_dir: Path,
    *,
    current_activity_log: Path,
    current_summary: Path,
) -> RetentionResult:
    if not logs_dir.exists():
        return RetentionResult()

    keep = {
        (logs_dir / "ingestion.log").resolve(),
        (logs_dir / "scheduler_run_latest.log").resolve(),
        (logs_dir / "ingestion_summary_latest.json").resolve(),
        current_activity_log.resolve(),
        current_summary.resolve(),
        (logs_dir / ".gitkeep").resolve(),
    }
    result = RetentionResult()

    for artifact in list(logs_dir.iterdir()):
        if not artifact.is_file() or artifact.resolve() in keep:
            continue
        if (
            artifact.name.startswith("scheduler_run_")
            or artifact.name.startswith("ingestion_summary_")
            or artifact.name.startswith("ingestion.log.")
        ):
            result += _remove_file(artifact)

    return result


def _remove_file(path: Path) -> RetentionResult:
    path.unlink(missing_ok=True)
    logger.info("Retention removed old file: %s", path)
    return RetentionResult(files_removed=1)


def _remove_directory(path: Path) -> RetentionResult:
    file_count = sum(1 for item in path.rglob("*") if item.is_file())
    shutil.rmtree(path)
    logger.info("Retention removed old directory: %s", path)
    return RetentionResult(files_removed=file_count, directories_removed=1)
