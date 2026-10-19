"""Installable Typer CLI; all commands use the same public pipeline functions."""

import json
import logging
import time
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from rich.console import Console
from rich.table import Table

from research_data_engine.config import PipelineConfig, load_config
from research_data_engine.exceptions import ResearchDataError
from research_data_engine.pipeline import ingest as run_ingestion
from research_data_engine.queries import DEFAULT_DATASET, QueryEngine
from research_data_engine.reporting import utc_now, write_json
from research_data_engine.sample_data import demo_config, write_sample_csv
from research_data_engine.storage import read_snapshot
from research_data_engine.validation import validate_prices

app = typer.Typer(
    help="Research Data Engine: validate, store, and query financial observations.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
console = Console()


def _fail(exc: Exception) -> None:
    console.print(f"Error: {exc}", markup=False)
    raise typer.Exit(1) from exc


def _resolve(dataset: str, config: Path) -> Path:
    """Explicit aliases; any other value must be an existing dataset directory."""
    path = Path(dataset)
    if path.is_dir():
        return path
    if config.is_file():
        settings = load_config(config)
        if dataset in {"prices", settings.dataset}:
            return settings.output.path
    elif dataset in {"prices", "equity_prices"}:
        return DEFAULT_DATASET
    raise ResearchDataError(
        f"Unknown dataset {dataset!r}; use 'prices' with --config or a dataset path"
    )


def _summary(report: dict) -> None:
    table = Table(title=f"Research Data Engine — {report['dataset']}")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for field in (
        "input_file_count",
        "input_row_count",
        "valid_row_count",
        "quarantined_row_count",
    ):
        table.add_row(field.replace("_", " "), str(report[field]))
    console.print(table)
    console.print("Errors: " + json.dumps(report["errors_by_category"], sort_keys=True))
    console.print("Warnings: " + json.dumps(report["warning_counts"], sort_keys=True))
    console.print("Output: " + report["output_location"])


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Emit structured pipeline logs")
    ] = False,
) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")


@app.command()
def ingest(
    config: Annotated[Path, typer.Option(help="YAML pipeline configuration")] = Path(
        "configs/prices.yaml"
    ),
) -> None:
    """Normalize, validate, calculate trailing analytics, and safely publish Parquet."""
    try:
        run = run_ingestion(config)
        _summary(run.report)
        console.print(f"Report: {run.snapshot.report_path}")
    except (ResearchDataError, OSError) as exc:
        _fail(exc)


@app.command()
def validate(
    dataset: Annotated[
        str, typer.Option(help="Dataset path or explicit 'prices' alias")
    ] = "prices",
    config: Annotated[Path, typer.Option()] = Path("configs/prices.yaml"),
    report: Annotated[Path | None, typer.Option(help="Optional JSON report destination")] = None,
) -> None:
    """Revalidate a snapshot using its recorded policies, without publishing a replacement."""
    try:
        started = time.perf_counter()
        timestamp = utc_now()
        snapshot = read_snapshot(_resolve(dataset, config))
        previous = json.loads(snapshot.report_path.read_text(encoding="utf-8"))
        settings = PipelineConfig.model_validate(previous["config"])
        result = validate_prices(pl.read_parquet(snapshot.prices_path), settings.validation)
        summary = {
            **previous,
            "execution_timestamp": timestamp,
            "validation_of_version": snapshot.version,
            "input_file_count": 1,
            "input_row_count": result.input_rows,
            "valid_row_count": result.clean.height,
            "quarantined_row_count": result.quarantine.height,
            "errors_by_category": result.errors,
            "warning_counts": result.warnings,
            "missing_values": result.missing_values,
            "missing_session_count": int(result.clean["_missing_sessions"].sum()),
            "processing_duration_seconds": time.perf_counter() - started,
            "duration_scope": "stored snapshot revalidation",
            "input_files": [{"path": str(snapshot.prices_path)}],
            "rejected_categories": result.rejected_categories,
            "status": "rejected" if result.errors else "valid",
        }
        if report:
            write_json(report, summary)
        _summary(summary)
        if result.errors:
            raise typer.Exit(1)
    except (ResearchDataError, OSError, pl.exceptions.PolarsError, ValueError) as exc:
        _fail(exc)


@app.command()
def query(
    sql: Annotated[Path, typer.Option(help="File containing one read-only SELECT")],
    dataset: Annotated[str, typer.Option()] = "prices",
    config: Annotated[Path, typer.Option()] = Path("configs/prices.yaml"),
    limit: Annotated[int, typer.Option(min=1, help="Maximum rows to display")] = 20,
) -> None:
    """Query the active Parquet snapshot through the DuckDB 'prices' view."""
    try:
        with QueryEngine(_resolve(dataset, config)) as engine:
            result = engine.query(sql.read_text(encoding="utf-8"))
        console.print(result.head(limit))
        console.print(f"{result.height:,} result rows; displaying at most {limit}.")
    except (ResearchDataError, OSError) as exc:
        _fail(exc)


@app.command()
def demo(
    directory: Annotated[
        Path, typer.Option(help="Artifacts directory; deterministic synthetic data")
    ] = Path("data"),
) -> None:
    """Generate five years of SYNTHETIC weekday prices, quarantine defects, and query results."""
    try:
        settings = demo_config(directory)
        console.print("SYNTHETIC data: 10 equities, 2021–2025; weekday calendar approximation.")
        write_sample_csv(settings.input.path, dirty=True)
        run = run_ingestion(settings)
        _summary(run.report)
        with QueryEngine(settings.output.path) as engine:
            console.print(
                engine.query("""
                SELECT symbol, source, count(*) AS observations,
                       avg(simple_return) AS avg_price_return,
                       avg(volume) AS avg_daily_volume
                FROM prices GROUP BY symbol, source ORDER BY symbol LIMIT 5
            """)
            )
        console.print(f"Report: {run.snapshot.report_path}")
        console.print(f"Quarantine: {run.snapshot.directory / 'quarantine.parquet'}")
    except (ResearchDataError, OSError, pl.exceptions.PolarsError) as exc:
        _fail(exc)


@app.command()
def benchmark(
    rows: Annotated[
        int, typer.Option(min=100, help="100000, 1000000, or optional 5000000")
    ] = 100_000,
    repetitions: Annotated[int, typer.Option(min=2, max=20)] = 3,
    output: Annotated[Path, typer.Option()] = Path("benchmarks/results"),
) -> None:
    """Verify equivalent outputs, then measure median wall time and process RSS."""
    from research_data_engine.benchmarking import run_benchmarks

    try:
        report = run_benchmarks(rows=rows, repetitions=repetitions, output=output)
        console.print(report["markdown"])
        console.print(f"Reports: {output / f'measured-{rows}.json'} and .md")
    except (ResearchDataError, OSError, ValueError) as exc:
        _fail(exc)
