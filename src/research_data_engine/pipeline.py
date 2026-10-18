"""Compose scanning, validation, audit reporting, and safe publication."""

import hashlib
import importlib.metadata
import logging
import platform
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from research_data_engine.config import PipelineConfig, load_config
from research_data_engine.exceptions import DataValidationError, IngestionError
from research_data_engine.ingestion import scan_prices
from research_data_engine.reporting import log_event, utc_now, write_json
from research_data_engine.storage import Snapshot, publish_snapshot
from research_data_engine.validation import validate_prices

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineRun:
    snapshot: Snapshot
    report: dict[str, Any]


def ingest(config: PipelineConfig | str | Path) -> PipelineRun:
    """Reject policies fail the entire run; quarantine policies retain all valid records."""
    if not isinstance(config, PipelineConfig):
        config = load_config(config)
    started = time.perf_counter()
    timestamp = utc_now()
    lazy, files = scan_prices(config)
    fingerprints = []
    file_states = {}
    for path in files:
        stat = path.stat()
        file_states[path] = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        with path.open("rb") as handle:
            fingerprints.append(
                {"path": str(path), "sha256": hashlib.file_digest(handle, "sha256").hexdigest()}
            )
    log_event(logger, "ingestion_started", dataset=config.dataset, input_files=len(files))
    try:
        normalized = lazy.collect(engine="streaming")
        for path, original in file_states.items():
            stat = path.stat()
            if (stat.st_ino, stat.st_size, stat.st_mtime_ns) != original:
                raise IngestionError(
                    f"Input changed during ingestion: {path}; retry with stable files"
                )
    except (OSError, pl.exceptions.PolarsError) as exc:
        raise IngestionError(f"CSV materialization failed: {exc}") from exc
    result = validate_prices(normalized, config.validation)
    report = {
        "dataset": config.dataset,
        "execution_timestamp": timestamp,
        "input_file_count": len(files),
        "input_row_count": result.input_rows,
        "valid_row_count": result.clean.height,
        "quarantined_row_count": result.quarantine.height,
        "warning_counts": result.warnings,
        "errors_by_category": result.errors,
        "missing_values": result.missing_values,
        "missing_session_count": int(result.clean["_missing_sessions"].sum()),
        "processing_duration_seconds": time.perf_counter() - started,
        "duration_scope": "scan, fingerprint, materialization, validation, analytics; "
        "excludes publication",
        "output_location": str(config.output.path.resolve()),
        "status": "rejected" if result.rejected else "published",
        "rejected_categories": result.rejected_categories,
        "input_files": fingerprints,
        "config": config.model_dump(mode="json", by_alias=True),
        "sources": sorted(result.clean["source"].unique().to_list()),
        "calendar": config.validation.calendar,
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "research-data-engine",
                "polars",
                "duckdb",
                "pyarrow",
                "pydantic",
            )
        },
    }
    if result.rejected:
        rejection = config.output.path.parent / "rejected" / uuid.uuid4().hex
        rejection.mkdir(parents=True, exist_ok=False)
        write_json(rejection / "report.json", report)
        result.quarantine.write_parquet(rejection / "quarantine.parquet", compression="zstd")
        log_event(
            logger,
            "ingestion_rejected",
            dataset=config.dataset,
            report=str(rejection / "report.json"),
        )
        raise DataValidationError(
            f"Dataset rejected for {result.rejected_categories}. "
            f"Report and quarantine: {rejection}. Previous snapshot remains active."
        )
    snapshot = publish_snapshot(config.output.path, result.clean, result.quarantine, report)
    log_event(
        logger,
        "snapshot_published",
        dataset=config.dataset,
        version=snapshot.version,
        valid_rows=result.clean.height,
        quarantined_rows=result.quarantine.height,
    )
    return PipelineRun(snapshot, report)
