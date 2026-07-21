from __future__ import annotations

import logging

from ingestion.logging_config import setup_ingestion_logging


def test_setup_ingestion_logging_creates_per_run_and_latest_logs(tmp_path) -> None:
    run_log = setup_ingestion_logging(tmp_path)
    logger = logging.getLogger("ingestion.scheduler_test")
    logger.info("scheduler activity test")

    ingestion_logger = logging.getLogger("ingestion")
    for handler in ingestion_logger.handlers:
        handler.flush()

    assert run_log.exists()
    assert run_log.name.startswith("scheduler_run_")
    assert "scheduler activity test" in run_log.read_text(encoding="utf-8")
    assert "scheduler activity test" in (
        tmp_path / "scheduler_run_latest.log"
    ).read_text(encoding="utf-8")
    assert "scheduler activity test" in (tmp_path / "ingestion.log").read_text(
        encoding="utf-8"
    )

    for handler in ingestion_logger.handlers:
        handler.close()
    ingestion_logger.handlers.clear()
