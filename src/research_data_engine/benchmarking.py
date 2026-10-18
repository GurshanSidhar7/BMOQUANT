"""Equivalent workloads, correctness gates, isolated workers, measured reports only."""

import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import polars as pl
import psutil
from polars.testing import assert_frame_equal

from research_data_engine.analytics import with_returns
from research_data_engine.exceptions import BenchmarkError
from research_data_engine.reporting import utc_now, write_json
from research_data_engine.sample_data import generate_prices
from research_data_engine.transformations import GROUPS, PRICE_SCHEMA, SORT_ORDER

START = date(2024, 1, 1)
END = date(2025, 1, 1)
WORKLOADS = {
    "A_csv_ingestion": "Read eight typed CSV columns, including dates; fully materialize.",
    "B_group_by": "Preloaded data: mean volume and simple price return by symbol/source.",
    "C_rolling": "Preloaded: sort and trailing 20-log-return sample volatility * sqrt(252).",
    "D_filter_aggregate": "Preloaded: filter 2024, project columns, grouped mean volume/return.",
    "E_parquet_query": "Read Parquet: filter 2024, project columns, grouped mean volume/return.",
}


def _pandas_aggregate(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(GROUPS, sort=True, observed=True)
        .agg(average_volume=("volume", "mean"), average_return=("simple_return", "mean"))
        .reset_index()
    )


def _polars_aggregate(frame: pl.LazyFrame) -> pl.DataFrame:
    return (
        frame.group_by(GROUPS)
        .agg(
            pl.col("volume").mean().alias("average_volume"),
            pl.col("simple_return").mean().alias("average_return"),
        )
        .sort(GROUPS)
        .collect()
    )


def prepare_workload(engine: str, workload: str, directory: Path) -> Callable[[], Any]:
    """Imports and preloading B/C/D occur outside the measured execution boundary."""
    csv = directory / "prices.csv"
    parquet = directory / "analytics.parquet"
    if workload == "A_csv_ingestion":
        if engine == "pandas":
            return lambda: pd.read_csv(
                csv,
                parse_dates=["date"],
                date_format="%Y-%m-%d",
                dtype={
                    "symbol": "str",
                    "source": "str",
                    "volume": "int64",
                    **{c: "float64" for c in ("open", "high", "low", "close")},
                },
            )
        return lambda: pl.read_csv(csv, schema_overrides=PRICE_SCHEMA, try_parse_dates=True)
    if workload == "E_parquet_query":
        if engine == "pandas":
            return lambda: _pandas_aggregate(
                pd.read_parquet(
                    parquet,
                    columns=[*GROUPS, "volume", "simple_return"],
                    filters=[("date", ">=", START), ("date", "<", END)],
                    engine="pyarrow",
                )
            )
        connection = duckdb.connect()
        # Connection setup excluded, just as imports and engine setup are excluded elsewhere.
        # Closure retains the connection until this workload is released.
        return lambda: connection.execute(
            """
            SELECT symbol, source, avg(volume) AS average_volume,
                   avg(simple_return) AS average_return
            FROM read_parquet(?) WHERE date >= ? AND date < ?
            GROUP BY symbol, source ORDER BY symbol, source
        """,
            [str(parquet), START, END],
        ).pl()
    if engine == "pandas":
        pandas_frame = pd.read_parquet(parquet, engine="pyarrow")
        # Parquet DATE defaults to Python date objects. Normalize once during setup
        # so the pandas baseline also uses vectorized datetime filtering/sorting.
        pandas_frame["date"] = pd.to_datetime(pandas_frame["date"])
        if workload == "B_group_by":
            return lambda: _pandas_aggregate(pandas_frame)
        if workload == "C_rolling":

            def rolling_pandas() -> pd.DataFrame:
                ordered = pandas_frame.sort_values(SORT_ORDER, kind="stable").reset_index(drop=True)
                volatility = ordered.groupby(GROUPS, sort=False, observed=True)[
                    "log_return"
                ].rolling(20, min_periods=20).std(ddof=1).reset_index(
                    level=GROUPS, drop=True
                ).sort_index() * math.sqrt(252)
                return ordered[[*GROUPS, "date"]].assign(volatility=volatility)

            return rolling_pandas
        return lambda: _pandas_aggregate(
            pandas_frame.loc[
                (pandas_frame["date"] >= pd.Timestamp(START))
                & (pandas_frame["date"] < pd.Timestamp(END)),
                [*GROUPS, "volume", "simple_return"],
            ]
        )
    polars_frame = pl.read_parquet(parquet)
    if workload == "B_group_by":
        return lambda: _polars_aggregate(polars_frame.lazy())
    if workload == "C_rolling":
        return lambda: (
            polars_frame.lazy()
            .sort(SORT_ORDER)
            .select(
                *GROUPS,
                "date",
                (
                    pl.col("log_return").rolling_std(20, min_samples=20, ddof=1).over(GROUPS)
                    * math.sqrt(252)
                ).alias("volatility"),
            )
            .collect()
        )
    return lambda: _polars_aggregate(
        polars_frame.lazy()
        .filter((pl.col("date") >= START) & (pl.col("date") < END))
        .select(*GROUPS, "volume", "simple_return")
    )


def _canonical(result: Any) -> pl.DataFrame:
    frame = pl.from_pandas(result) if isinstance(result, pd.DataFrame) else result
    if "date" in frame.columns:
        frame = frame.with_columns(pl.col("date").cast(pl.Date))
    return frame.sort([c for c in (*GROUPS, "date") if c in frame.columns])


def verify_equivalence(baseline: Any, candidate: Any, *, workload: str) -> None:
    """Compare all rows, null patterns, keys, and numerical outputs before timing."""
    try:
        assert_frame_equal(
            _canonical(baseline),
            _canonical(candidate),
            check_dtypes=False,
            rel_tol=1e-8,
            abs_tol=1e-10,
        )
    except (AssertionError, TypeError, ValueError) as exc:
        raise BenchmarkError(f"Correctness gate failed for {workload}: {exc}") from exc


def _monitor_rss(
    process: psutil.Process, peak: list[int], stop: threading.Event, ready: threading.Event
) -> None:
    ready.set()
    while not stop.wait(0.002):
        peak[0] = max(peak[0], process.memory_info().rss)


def measure_workload(
    *,
    engine: str,
    workload: str,
    directory: Path,
    repetitions: int,
) -> dict[str, Any]:
    """One isolated process per workload/engine, one warmup, sampled whole-process RSS.

    Peak RSS is sampled every 2 ms, including native allocations. Absolute RSS
    includes Python, imports, input data, and retained allocator memory. The delta
    is relative to RSS immediately before each timed call, not memory allocated.
    """
    operation = prepare_workload(engine, workload, directory)
    warmup = operation()
    del warmup
    samples = []
    process = psutil.Process()
    for _ in range(repetitions):
        gc.collect()
        baseline_rss = process.memory_info().rss
        peak = [baseline_rss]
        stop = threading.Event()
        ready = threading.Event()

        sampler = threading.Thread(
            target=_monitor_rss, args=(process, peak, stop, ready), daemon=True
        )
        sampler.start()
        ready.wait()
        cpu_started = time.process_time()
        started = time.perf_counter()
        try:
            result = operation()
            elapsed = time.perf_counter() - started
            cpu_elapsed = time.process_time() - cpu_started
            peak[0] = max(peak[0], process.memory_info().rss)
        finally:
            stop.set()
            sampler.join()
        samples.append(
            {
                "wall_seconds": elapsed,
                "cpu_seconds": cpu_elapsed,
                "baseline_rss_bytes": baseline_rss,
                "sampled_peak_rss_bytes": peak[0],
                "sampled_rss_increase_bytes": max(peak[0] - baseline_rss, 0),
                "result_rows": len(result),
            }
        )
        del result
    return {
        "engine": engine,
        "workload": workload,
        "samples": samples,
        "median_wall_seconds": statistics.median(s["wall_seconds"] for s in samples),
        "median_cpu_seconds": statistics.median(s["cpu_seconds"] for s in samples),
        "median_sampled_peak_rss_bytes": statistics.median(
            s["sampled_peak_rss_bytes"] for s in samples
        ),
        "median_sampled_rss_increase_bytes": statistics.median(
            s["sampled_rss_increase_bytes"] for s in samples
        ),
    }


def _hardware() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": psutil.cpu_count(),
        "physical_cpus": psutil.cpu_count(logical=False),
        "physical_memory_bytes": psutil.virtual_memory().total,
        "polars_threads": pl.thread_pool_size(),
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "POLARS_MAX_THREADS",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
            )
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    rows = report["rows"]
    lines = [
        f"# Measured benchmark: {rows:,} SYNTHETIC observations",
        "",
        f"Executed: {report['execution_timestamp']}. "
        f"Seed 42; {report['repetitions']} repetitions; one warmup.",
        "Correctness: every candidate passed full-result comparison before timing.",
        "",
        "| Workload | Engine | Median wall ms | Median CPU ms | "
        "Sampled peak RSS MiB | RSS increase MiB | Speedup vs pandas |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for record in report["measurements"]:
        lines.append(
            f"| {record['workload']} | {record['engine']} | "
            f"{record['median_wall_seconds'] * 1000:.3f} | "
            f"{record['median_cpu_seconds'] * 1000:.3f} | "
            f"{record['median_sampled_peak_rss_bytes'] / 2**20:.2f} | "
            f"{record['median_sampled_rss_increase_bytes'] / 2**20:.2f} | "
            f"{record['speedup_vs_pandas']:.2f}x |"
        )
    lines.extend(["", "## Execution boundaries", ""])
    lines.extend(f"- **{key}:** {value}" for key, value in WORKLOADS.items())
    lines.extend(
        [
            "",
            "Generation, input writes, imports, correctness checks, startup, "
            "and B/C/D preloads are excluded.",
            "Parquet E uses pandas/PyArrow pushdown versus DuckDB direct SQL; "
            "their execution models differ.",
            "DuckDB materializes a Polars result; pandas returns a pandas result. "
            "OS caches are warm; this is not a cold-disk benchmark.",
            "RSS is sampled every 2 ms in isolated engine/workload processes. "
            "Peaks may be missed for short calls.",
            "Absolute RSS includes imports, inputs, and allocator retention; "
            "increases are not total allocated bytes.",
            "CPU time includes native threads and sampler; wall time is elapsed time. "
            "Sub-1x means slower than pandas.",
            "Speedup = median pandas wall / median candidate wall. "
            "No cross-machine performance guarantee.",
            "",
            "## Environment",
            "",
            "```json",
            json.dumps(
                {
                    "python": report["python"],
                    "packages": report["packages"],
                    "hardware": report["hardware"],
                },
                indent=2,
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def run_benchmarks(
    *,
    rows: int = 100_000,
    repetitions: int = 3,
    output: str | Path = "benchmarks/results",
) -> dict[str, Any]:
    """Support arbitrary positive scales; 5M is optional and requires sufficient RAM."""
    if rows < 100 or not 2 <= repetitions <= 20:
        raise ValueError("Use at least 100 rows and 2–20 repetitions")
    measurements = []
    fingerprints = {}
    # Approximately five observed years per symbol even for the optional 5M scale.
    symbols = max(1, math.ceil(rows / 1304))
    with tempfile.TemporaryDirectory(prefix="research-data-benchmark-") as temporary:
        directory = Path(temporary)
        raw = generate_prices(symbols=symbols, rows=rows)
        raw.write_csv(directory / "prices.csv")
        with_returns(raw.lazy()).collect().write_parquet(
            directory / "analytics.parquet", compression="zstd"
        )
        del raw
        for filename in ("prices.csv", "analytics.parquet"):
            with (directory / filename).open("rb") as handle:
                fingerprints[filename] = hashlib.file_digest(handle, "sha256").hexdigest()
        # Gate every workload before recording any timing results.
        for workload in WORKLOADS:
            candidate = "duckdb" if workload == "E_parquet_query" else "polars"
            baseline_operation = prepare_workload("pandas", workload, directory)
            candidate_operation = prepare_workload(candidate, workload, directory)
            verify_equivalence(baseline_operation(), candidate_operation(), workload=workload)
            del baseline_operation, candidate_operation
        for workload in WORKLOADS:
            candidate = "duckdb" if workload == "E_parquet_query" else "polars"
            for engine in ("pandas", candidate):
                command = [
                    sys.executable,
                    "-m",
                    "research_data_engine._benchmark_worker",
                    "--engine",
                    engine,
                    "--workload",
                    workload,
                    "--directory",
                    str(directory),
                    "--repetitions",
                    str(repetitions),
                ]
                completed = subprocess.run(command, capture_output=True, text=True, check=False)
                if completed.returncode:
                    raise BenchmarkError(
                        f"Worker failed ({engine}, {workload}): {completed.stderr}"
                    )
                try:
                    measurements.append(json.loads(completed.stdout))
                except json.JSONDecodeError as exc:
                    raise BenchmarkError(
                        f"Worker returned invalid output: {completed.stdout}"
                    ) from exc
    for record in measurements:
        baseline = next(
            m
            for m in measurements
            if m["workload"] == record["workload"] and m["engine"] == "pandas"
        )
        record["speedup_vs_pandas"] = (
            baseline["median_wall_seconds"] / record["median_wall_seconds"]
        )
    report = {
        "execution_timestamp": utc_now(),
        "data": "SYNTHETIC unadjusted weekday-calendar prices",
        "rows": rows,
        "symbols": symbols,
        "seed": 42,
        "repetitions": repetitions,
        "correctness": "all five full-result comparisons passed; rtol=1e-8, atol=1e-10",
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "research-data-engine",
                "polars",
                "duckdb",
                "pandas",
                "numpy",
                "pyarrow",
                "psutil",
            )
        },
        "hardware": _hardware(),
        "input_sha256": fingerprints,
        "workloads": WORKLOADS,
        "measurements": measurements,
        "methodology": "Isolated process per engine/workload; one warmup; median wall and CPU; "
        "2ms sampled whole-process RSS; warm OS cache; setup excluded; see docs/benchmarking.md.",
    }
    markdown = _markdown(report)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / f"measured-{rows}.json", report)
    (output / f"measured-{rows}.md").write_text(markdown, encoding="utf-8")
    return {**report, "markdown": markdown}
