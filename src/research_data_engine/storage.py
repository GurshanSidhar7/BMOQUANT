"""Immutable snapshots selected by an atomic CURRENT.json replacement."""

import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from research_data_engine.exceptions import StorageError
from research_data_engine.reporting import write_json
from research_data_engine.transformations import PRICE_SCHEMA, SORT_ORDER

FORMAT = "research-data-engine-v1"


@dataclass(frozen=True)
class Snapshot:
    root: Path
    version: str

    @property
    def directory(self) -> Path:
        return self.root / "versions" / self.version

    @property
    def prices_path(self) -> Path:
        return self.directory / "prices.parquet"

    @property
    def report_path(self) -> Path:
        return self.directory / "report.json"


def read_snapshot(root: str | Path) -> Snapshot:
    root = Path(root).resolve()
    try:
        pointer = json.loads((root / "CURRENT.json").read_text(encoding="utf-8"))
        version = pointer["version"]
        if pointer.get("format") != FORMAT or not re.fullmatch(r"[0-9a-f]{32}", version):
            raise ValueError("Invalid snapshot manifest")
        snapshot = Snapshot(root, version)
        if not snapshot.prices_path.is_file() or not snapshot.report_path.is_file():
            raise ValueError("Snapshot is incomplete")
        return snapshot
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise StorageError(
            f"Cannot resolve dataset {root}: {exc}; run ingest or demo first"
        ) from exc


def _ensure_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "dataset.json"
    if marker.exists():
        if json.loads(marker.read_text(encoding="utf-8")) != {"format": FORMAT}:
            raise ValueError("Unknown dataset format")
    else:
        if any(root.iterdir()):
            raise ValueError("Refusing to publish into a nonempty, unmanaged directory")
        write_json(marker, {"format": FORMAT})
    (root / "versions").mkdir(exist_ok=True)


def _publish_pointer(temporary: Path, target: Path) -> None:
    """The sole visibility boundary, isolated for failure-injection tests."""
    os.replace(temporary, target)


def publish_snapshot(
    root: str | Path,
    prices: pl.DataFrame,
    quarantine: pl.DataFrame,
    report: dict[str, Any],
) -> Snapshot:
    """Publish one complete run; old snapshots are retained, never globbed together.

    Requires a local filesystem with atomic same-directory os.replace. Concurrent
    writers are outside the supported MVP contract; use a single writer per dataset.
    """
    root = Path(root).resolve()
    stage = None
    final = None
    pointer_temp = None
    try:
        for name, dtype in PRICE_SCHEMA.items():
            if prices.schema.get(name) != dtype:
                raise ValueError(f"Output column {name} must have type {dtype}")
        _ensure_root(root)
        if (root / "CURRENT.json").exists():
            read_snapshot(root)  # Do not replace a corrupt or unknown active manifest.
        version = uuid.uuid4().hex
        stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
        final = root / "versions" / version
        prices.sort(SORT_ORDER).write_parquet(stage / "prices.parquet", compression="zstd")
        quarantine.write_parquet(stage / "quarantine.parquet", compression="zstd")
        write_json(stage / "report.json", report)
        write_json(stage / "metadata.json", {"format": FORMAT, "version": version, **report})
        for artifact in stage.iterdir():
            with artifact.open("rb") as handle:
                os.fsync(handle.fileno())
        os.replace(stage, final)
        pointer_temp = root / f".CURRENT-{version}.tmp"
        write_json(pointer_temp, {"format": FORMAT, "version": version})
        with pointer_temp.open("rb") as handle:
            os.fsync(handle.fileno())
        _publish_pointer(pointer_temp, root / "CURRENT.json")
        return Snapshot(root, version)
    except (OSError, ValueError, pl.exceptions.PolarsError, StorageError) as exc:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        if final is not None and final.exists():
            shutil.rmtree(final)
        if pointer_temp is not None:
            pointer_temp.unlink(missing_ok=True)
        raise StorageError(f"Snapshot publication failed at {root}: {exc}") from exc
