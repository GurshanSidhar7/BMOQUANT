# Measured benchmark: 100,000 SYNTHETIC observations

Executed: 2026-10-18T20:38:22.825195+00:00. Seed 42; 3 repetitions; one warmup.
Correctness: every candidate passed full-result comparison before timing.

| Workload | Engine | Median wall ms | Median CPU ms | Sampled peak RSS MiB | RSS increase MiB | Speedup vs pandas |
|---|---|---:|---:|---:|---:|---:|
| A_csv_ingestion | pandas | 72.598 | 71.782 | 173.33 | 0.06 | 1.00x |
| A_csv_ingestion | polars | 5.067 | 29.075 | 171.70 | 13.61 | 14.33x |
| B_group_by | pandas | 6.547 | 6.590 | 191.81 | 0.03 | 1.00x |
| B_group_by | polars | 1.702 | 8.689 | 180.44 | 0.67 | 3.85x |
| C_rolling | pandas | 12.811 | 12.914 | 197.12 | 0.03 | 1.00x |
| C_rolling | polars | 4.110 | 12.680 | 196.64 | 4.95 | 3.12x |
| D_filter_aggregate | pandas | 4.421 | 4.448 | 188.69 | 0.03 | 1.00x |
| D_filter_aggregate | polars | 1.488 | 6.680 | 178.09 | 0.58 | 2.97x |
| E_parquet_query | pandas | 6.576 | 10.599 | 187.33 | 6.58 | 1.00x |
| E_parquet_query | duckdb | 3.924 | 8.096 | 161.31 | 0.09 | 1.68x |

## Execution boundaries

- **A_csv_ingestion:** Read eight typed CSV columns, including dates; fully materialize.
- **B_group_by:** Preloaded data: mean volume and simple price return by symbol/source.
- **C_rolling:** Preloaded: sort and trailing 20-log-return sample volatility * sqrt(252).
- **D_filter_aggregate:** Preloaded: filter 2024, project columns, grouped mean volume/return.
- **E_parquet_query:** Read Parquet: filter 2024, project columns, grouped mean volume/return.

Generation, input writes, imports, correctness checks, startup, and B/C/D preloads are excluded.
Parquet E uses pandas/PyArrow pushdown versus DuckDB direct SQL; their execution models differ.
DuckDB materializes a Polars result; pandas returns a pandas result. OS caches are warm; this is not a cold-disk benchmark.
RSS is sampled every 2 ms in isolated engine/workload processes. Peaks may be missed for short calls.
Absolute RSS includes imports, inputs, and allocator retention; increases are not total allocated bytes.
CPU time includes native threads and sampler; wall time is elapsed time. Sub-1x means slower than pandas.
Speedup = median pandas wall / median candidate wall. No cross-machine performance guarantee.

## Environment

```json
{
  "python": "3.12.15",
  "packages": {
    "research-data-engine": "0.1.0",
    "polars": "1.44.2",
    "duckdb": "1.5.6",
    "pandas": "3.0.6",
    "numpy": "2.5.4",
    "pyarrow": "24.0.0",
    "psutil": "7.2.2"
  },
  "hardware": {
    "platform": "macOS-26.5.2-arm64-arm-64bit",
    "machine": "arm64",
    "processor": "arm",
    "logical_cpus": 8,
    "physical_cpus": 8,
    "physical_memory_bytes": 8589934592,
    "polars_threads": 8,
    "thread_environment": {
      "POLARS_MAX_THREADS": null,
      "OMP_NUM_THREADS": null,
      "OPENBLAS_NUM_THREADS": null
    }
  }
}
```
