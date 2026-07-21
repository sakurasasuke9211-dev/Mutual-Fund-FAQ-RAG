import json
from pathlib import Path

from ingestion.retention import prune_generated_artifacts


def _write(path: Path, content: str = "test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_prune_generated_artifacts_keeps_only_current_outputs(tmp_path) -> None:
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    slug = "current-scheme"

    scheme_raw = data_dir / "raw" / slug
    current_html = _write(scheme_raw / "current.html")
    current_normalized = _write(scheme_raw / "current.normalized.txt")
    current_meta = _write(scheme_raw / "current.meta.json")
    _write(scheme_raw / "old.html")
    _write(scheme_raw / "old.normalized.txt")
    _write(data_dir / "raw" / "_debug.html")
    _write(
        scheme_raw / "latest.json",
        json.dumps(
            {
                "raw_path": str(current_html),
                "normalized_path": str(current_normalized),
                "meta_path": str(current_meta),
            }
        ),
    )

    for component in ("parsed", "facts", "chunks"):
        scheme_dir = data_dir / component / slug
        _write(scheme_dir / "latest.json")
        _write(scheme_dir / "history" / "old.json")
        _write(data_dir / component / "removed-scheme" / "latest.json")
    _write(data_dir / "facts" / "catalog.json")
    _write(data_dir / "chunks" / "catalog.json")

    current_log = _write(logs_dir / "scheduler_run_current.log")
    _write(logs_dir / "scheduler_run_latest.log")
    _write(logs_dir / "scheduler_run_old.log")
    _write(logs_dir / "ingestion.log")
    _write(logs_dir / "ingestion.log.1")
    current_summary = _write(logs_dir / "ingestion_summary_current.json")
    _write(logs_dir / "ingestion_summary_latest.json")
    _write(logs_dir / "ingestion_summary_old.json")

    result = prune_generated_artifacts(
        current_activity_log=current_log,
        current_summary=current_summary,
        data_dir=data_dir,
        logs_dir=logs_dir,
        active_slugs={slug},
    )

    assert result.files_removed > 0
    assert current_html.exists()
    assert current_normalized.exists()
    assert current_meta.exists()
    assert not (scheme_raw / "old.html").exists()
    assert not (data_dir / "raw" / "_debug.html").exists()

    for component in ("parsed", "facts", "chunks"):
        assert (data_dir / component / slug / "latest.json").exists()
        assert not (data_dir / component / slug / "history").exists()
        assert not (data_dir / component / "removed-scheme").exists()

    assert current_log.exists()
    assert current_summary.exists()
    assert not (logs_dir / "scheduler_run_old.log").exists()
    assert not (logs_dir / "ingestion_summary_old.json").exists()
    assert not (logs_dir / "ingestion.log.1").exists()


def test_prune_raw_skips_scheme_when_latest_is_malformed(tmp_path) -> None:
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    scheme_dir = data_dir / "raw" / "current-scheme"
    old_file = _write(scheme_dir / "old.html")
    _write(scheme_dir / "latest.json", "{not-json")
    current_log = _write(logs_dir / "scheduler_run_current.log")
    current_summary = _write(logs_dir / "ingestion_summary_current.json")

    prune_generated_artifacts(
        current_activity_log=current_log,
        current_summary=current_summary,
        data_dir=data_dir,
        logs_dir=logs_dir,
        active_slugs={"current-scheme"},
    )

    assert old_file.exists()
