from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ingestion.config import LOGS_DIR


def setup_ingestion_logging(logs_dir: Path | None = None) -> Path:
    """Configure console, current-run, and timestamped ingestion activity logs."""
    target_dir = logs_dir or LOGS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    cumulative_log = target_dir / "ingestion.log"
    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")
    run_log = target_dir / f"scheduler_run_{run_timestamp}.log"
    latest_log = target_dir / "scheduler_run_latest.log"
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    cumulative_handler = logging.FileHandler(cumulative_log, mode="w", encoding="utf-8")
    cumulative_handler.setFormatter(formatter)

    run_handler = logging.FileHandler(run_log, encoding="utf-8")
    run_handler.setFormatter(formatter)

    latest_handler = logging.FileHandler(latest_log, mode="w", encoding="utf-8")
    latest_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger("ingestion")
    root.setLevel(logging.INFO)
    for existing_handler in root.handlers:
        existing_handler.close()
    root.handlers.clear()
    root.addHandler(cumulative_handler)
    root.addHandler(run_handler)
    root.addHandler(latest_handler)
    root.addHandler(stream_handler)
    root.propagate = False

    return run_log


def write_job_summary(summary_path: Path, payload: dict) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
