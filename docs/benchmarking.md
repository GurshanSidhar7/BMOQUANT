# Benchmark methodology and interpretation

The benchmark asks **where Polars or DuckDB provide measurable benefits relative to pandas**, not which library always wins. All observations are deterministically generated **synthetic unadjusted weekday prices**. No investment inference follows from them.

## Reproduce

```bash
uv run research-data benchmark --rows 100000 --repetitions 3
uv run research-data benchmark --rows 1000000 --repetitions 3
# Optional; not part of the required verification and not executed for this delivery:
uv run research-data benchmark --rows 5000000 --repetitions 3
```

Each command writes `benchmarks/results/measured-<rows>.json` and `.md`. The committed reports for [100k](../benchmarks/results/measured-100000.md) and [1M](../benchmarks/results/measured-1000000.md) contain actual measurements, individual samples, environment information, and input hashes. The 5M scale is supported but **not executed** in this delivery; no 5M performance is claimed. Temporary input datasets are removed after each benchmark.

## Equivalent workloads

| ID | Timed work | Candidate |
|---|---|---|
| A | CSV read of eight explicitly typed columns including date parsing, full materialization | Polars eager CSV read vs pandas CSV read |
| B | Preloaded group-by mean volume and mean simple price return per symbol/source, sorted result | Polars lazy expression collection vs pandas group-by |
| C | Preloaded sort and full trailing 20-log-return sample volatility × sqrt(252), all result rows | Polars window expressions vs pandas grouped rolling |
| D | Preloaded 2024 date filter, relevant-column projection, grouped means, sorted result | Polars lazy filter/aggregation vs pandas vectorized filtering/group-by |
| E | Parquet projection/date filtering and grouped means, sorted result | DuckDB direct SQL vs pandas/PyArrow `read_parquet` with `columns` and `filters` |

The data has approximately five observed years per symbol; symbol count grows with the row scale instead of extending dates hundreds of years. Seed 42, date boundaries, source groups, Float64 columns, and window definitions are identical. Common precomputed returns/log returns are written once and loaded for B–E. This isolates the stated operations; B–E do not benchmark return construction. C includes sorting, returns all dated rows, uses `ddof=1`, requires 20 non-null log returns, and has identical leading nulls.

The pandas setup converts Parquet Date objects to a vectorized datetime dtype **outside** timed B/C/D calls. Filters use Timestamp bounds. pandas therefore does not incur avoidable Python-date filtering overhead. pandas CSV uses its normal parser with explicit dtypes/date format. E gives PyArrow predicate/column pushdown rather than handicapping pandas by loading every column first. SQL/Arrow and DataFrame execution models still differ; E intentionally compares end-to-end ways to answer the same Parquet question.

## Correctness before performance

All five workloads execute in the controller before **any** timed measurements are recorded. Every candidate is compared to pandas across the full result: group/date keys, column names, row counts, null patterns, and numerical values. Date representations are normalized only for comparison, outside timing. Tolerance is relative `1e-8` and absolute `1e-10`. The gate raises `BenchmarkError` on mismatch and does not create a new successful report. The test suite deliberately passes a wrong result to ensure the gate fails.

Numerical equivalence is not a substitute for financial correctness: separate analytics tests compare log returns and rolling volatility to explicit mathematical/NumPy references, and DuckDB window statistics to Polars.

## Timing and memory

Each engine/workload runs in a separate fresh Python subprocess, avoiding allocator contamination from a previously measured competing engine. Within it, imports, initialization, B/C/D preloading, and one warmup occur before timing. Three repetitions are used in the delivered reports; the CLI supports 2–20. Each repetition explicitly materializes its full native result. DuckDB E converts to a Polars result in the timed call; pandas returns pandas. Generation, writes, correctness checks, process startup, result comparison, and report serialization are excluded.

Both median **wall-clock elapsed time** (`perf_counter`) and process **CPU time** (`process_time`, including native threads and sampler activity) are recorded. Native parallelism can reduce elapsed time without reducing total CPU. Defaults are used; the report records CPU counts, Polars thread count, and relevant thread environment overrides. CPU time is not interchangeable with wall time.

Memory uses `psutil` whole-process resident set size, sampled by a background thread every **2 ms**, plus start/end observations. This includes native Polars/DuckDB/Arrow allocations that Python `tracemalloc` would miss. Reports give absolute sampled peak RSS and increase above the RSS immediately before each timed call. Absolute RSS includes imports, preloaded inputs, and allocator retention from warmup/prior repetitions. An increase of zero does **not** mean zero memory use or zero allocations. Short-lived peaks may be missed, especially for millisecond calls. These are measured sampled peaks, not precise allocator accounting or OS high-water marks.

Data generation and preflight checks warm the OS file cache. This is a warm-cache benchmark, not a cold-disk/uncached-storage result. Short calls are sensitive to scheduling and sampler overhead. Measurements run sequentially; no competing test suite is deliberately run during benchmark timing. The report records Python and package versions, OS/architecture, processor label, physical/logical CPUs, physical memory, input SHA-256 values, all repetitions, and UTC execution time. On the delivered macOS sandbox run, PyArrow emitted notices that CPU-cache/NEON `sysctl` discovery was denied; processing and correctness checks succeeded. Those environment limits further discourage extrapolating the numbers to another machine.

Speedup is **median pandas wall time / median candidate wall time**. Below 1× means the candidate is slower. Do not average incompatible workloads into one universal speedup. Report measured values, whether favorable or unfavorable, and never treat memory figures as proof that one engine always needs less memory.

## What these experiments do not establish

They do not measure live-market datasets, full validation pipeline throughput, cold storage, network I/O, Python startup latency, concurrent workloads, all possible pandas optimizations, huge-cardinality joins, or distributed computation. Three repetitions characterize this demonstration, not a formal performance study. The retained inputs have a simple synthetic distribution and symbol-major ordering. Results can change with sorting, group cardinality, row-group layout, compression, string representation, hardware, versions, thread settings, and machine load.

To extend the study, preserve correctness checks, add a clearly defined workload, choose representative data/cardinality, record setup/materialization boundaries, and retain the full report. If memory is limited, reduce rows rather than publishing an unexecuted or fabricated 5M result.
