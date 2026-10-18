# Measured benchmark: 1,000,000 SYNTHETIC observations

Executed: 2026-10-18T20:38:36.329137+00:00. Seed 42; 3 repetitions; one warmup.
Correctness: every candidate passed full-result comparison before timing.

| Workload | Engine | Median wall ms | Median CPU ms | Sampled peak RSS MiB | RSS increase MiB | Speedup vs pandas |
|---|---|---:|---:|---:|---:|---:|
| A_csv_ingestion | pandas | 657.353 | 640.814 | 312.56 | 2.25 | 1.00x |
| A_csv_ingestion | polars | 44.646 | 282.215 | 404.47 | 121.69 | 14.72x |
| B_group_by | pandas | 56.641 | 55.261 | 361.25 | 0.03 | 1.00x |
| B_group_by | polars | 11.389 | 54.678 | 225.78 | 0.69 | 4.97x |
| C_rolling | pandas | 124.828 | 123.518 | 418.70 | 0.05 | 1.00x |
| C_rolling | polars | 64.154 | 155.732 | 443.30 | 61.12 | 1.95x |
| D_filter_aggregate | pandas | 22.097 | 22.143 | 446.97 | 0.03 | 1.00x |
| D_filter_aggregate | polars | 3.551 | 20.535 | 289.12 | 1.69 | 6.22x |
| E_parquet_query | pandas | 35.347 | 98.232 | 309.05 | 53.77 | 1.00x |
| E_parquet_query | duckdb | 9.072 | 50.511 | 198.61 | 4.59 | 3.90x |

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
