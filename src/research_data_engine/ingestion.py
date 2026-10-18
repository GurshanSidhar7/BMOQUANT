"""Deterministic CSV discovery and lazy scanning with record-level provenance."""

from pathlib import Path

import polars as pl

from research_data_engine.config import PipelineConfig
from research_data_engine.exceptions import IngestionError
from research_data_engine.transformations import normalize_prices


def discover_csv_files(path: str | Path) -> list[Path]:
    path = Path(path).resolve()
    files = (
        sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() == ".csv")
        if path.is_dir()
        else [path]
    )
    if not files or any(not p.is_file() or p.suffix.lower() != ".csv" for p in files):
        raise IngestionError(f"No readable CSV input files at {path}; generate sample data first")
    return files


def scan_prices(config: PipelineConfig) -> tuple[pl.LazyFrame, list[Path]]:
    """Read all fields as strings so type inference cannot silently change the contract."""
    files = discover_csv_files(config.input.path)
    frames = []
    for path in files:
        try:
            raw = pl.scan_csv(
                path,
                infer_schema=False,
                row_index_name="_source_row",
                row_index_offset=2,
                raise_if_empty=False,
            ).with_columns(pl.lit(str(path)).alias("_source_file"))
            frames.append(normalize_prices(raw, config))
        except (pl.exceptions.PolarsError, OSError, IngestionError) as exc:
            raise IngestionError(f"Cannot scan {path}: {exc}") from exc
    return pl.concat(frames, how="vertical"), files
