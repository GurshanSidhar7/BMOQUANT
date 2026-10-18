# Interview walkthrough — Tuesday, October 20, 2026

This is an independent portfolio project. Do not imply that BMO commissioned, uses, or endorses it. Demonstrations and benchmarks use **synthetic prices**. Describe what the code and saved results actually demonstrate.

## A. Thirty-second introduction

“I built Research Data Engine to make repeated financial data cleaning reproducible. It takes messy OHLCV CSVs, normalizes them with Polars, applies explicit financial rules, and preserves invalid records in quarantine. It publishes typed Parquet snapshots and exposes them through DuckDB SQL and a Python API. I focused on verifiable financial calculations, safe reruns, and measured performance. The examples are synthetic, and the project is independent of BMO.”

## B. Ninety-second technical walkthrough

“The input contract is YAML validated by Pydantic. CSV discovery is deterministic, and Polars scans all raw fields as strings so one file's inferred types cannot silently change the schema. Lazy expressions normalize symbols, parse dates, and cast numbers while retaining raw values and file/record provenance.

“Validation distinguishes hard errors from warnings. Nonpositive prices, inconsistent OHLC ranges, negative volumes, parse failures, and duplicate observation keys use explicit quarantine or rejection policies. Every duplicate member is quarantined. An extreme price move stays in the data with a warning because it could be legitimate. The observation key and all lag calculations include source, so feeds are not silently merged.

“I calculate price and log returns and trailing sample volatility after validation. Full 20/30-return windows need 21/31 prices. I preserve source boundaries and historical context, test against NumPy, and never interpolate missing sessions.

“Each run writes an immutable compressed Parquet snapshot and then switches one manifest. DuckDB queries that snapshot directly. Benchmarks verify complete result equivalence before timing. On this machine, one-million-row CSV ingestion favored Polars by 14.72×, sorted rolling volatility by 1.95×, and the Parquet aggregate favored DuckDB by 3.90×. Those are measured warm-cache workloads, not universal guarantees.”

## C. Five architectural decisions and trade-offs

1. **Polars expressions with a deliberate materialization boundary.** Lazy normalization and scan pushdown are useful; full duplicate/quarantine reporting still needs an in-memory global view. Simplicity and correctness are favored over claiming out-of-core scale.
2. **All-member duplicate quarantine and independent sources.** No arbitrary first/last choice or silent feed priority. It can discard more usable observations than a reviewed source-ranking policy, but it makes ambiguity explicit.
3. **Parquet snapshots with an atomic manifest.** Typed compressed data, no append duplication, prior snapshots available to readers. Retention consumes disk; concurrent writers and distributed publication are not implemented.
4. **DuckDB as the local SQL layer.** Direct Parquet OLAP without a server. PostgreSQL would serve centralized transactional/multi-user requirements better. The SQL restrictions are local safeguards, not a hostile-query sandbox.
5. **Correctness-gated, scoped benchmarks.** Full results, nulls, and window definitions match before timing; independent worker processes, warmup, medians, and native RSS measurements. Warm caches, three repetitions, synthetic distributions, and sampled memory limit generalization.

## D. Ten likely technical questions

### 1. Why use Polars?

It expresses normalization and financial validation as column operations and can optimize lazy scans and use native parallelism. The measured workloads support using it here, but pandas remains convenient for small analyses and ecosystem integrations. Sorting and materialization can still require substantial memory. Discuss measured workload-specific results, not a blanket claim that Polars always wins.

### 2. Why DuckDB instead of PostgreSQL?

The user is a researcher querying local Parquet files, so an embedded analytical engine removes service setup and data copying. PostgreSQL becomes attractive for shared operational data, concurrent transactional writes, identity/access control, or an existing managed platform. This MVP is not a centralized market-data service.

### 3. What is lazy evaluation?

A LazyFrame describes a computation without immediately producing its rows. At `collect`, Polars optimizes and executes the plan. This allows transformations to be combined or moved, but it does not automatically make global sorts or duplicate detection memory-free. Our benchmark includes `collect`; it never times only lazy plan construction.

### 4. What is predicate pushdown?

Move a filter toward the scan so the engine can avoid unnecessary rows or row groups. Projection pushdown similarly selects only needed columns. `examples/research_example.py` prints the optimized Parquet plan. Physical savings depend on statistics and data layout; a pushed filter does not guarantee every row group can be skipped. Filtering before calculating lagged returns can change their meaning, so the public slices filter stored analytics afterward.

### 5. Why Parquet?

It preserves types, compresses columnar data, and lets analytical readers project columns and filter row groups. CSV is a useful raw interchange format but requires parsing and lacks a reliable stored schema. Tiny partitions would add overhead here, so each snapshot has one clean file and one quarantine file.

### 6. How do you detect duplicates?

Polars computes the group size over `(symbol, date, source)` across all discovered files. Any size above one marks every group member. Identical duplicates and conflicting duplicate values both quarantine. Different sources stay separate; source priority and security-master reconciliation are future work.

### 7. How do you validate financial prices?

Require finite, positive OHLC, nonnegative integer volume, high at least open/close/low, and low at most open/close/high. Detect nulls, parse failures, duplicate keys, and nonfinite derived values. Keep raw mapped fields with reasons. Large returns, volume changes, and stale closes are warnings. A valid-looking value is not necessarily economically correct; adjustments and vendor reconciliation are not implemented.

### 8. How do you prevent data leakage?

Lags and trailing windows group by symbol/source, use deterministic date order, and include only the current and prior retained observations. Tests confirm appending future rows does not change history. API date slices retain already-calculated pre-start context. Closing prices/volumes are only known after the close: a strategy using these features must model later execution/availability. The app does not implement point-in-time fundamentals, revision timestamps, or a backtest execution model, so do not claim broader leakage prevention.

### 9. How would you scale the pipeline?

Profile actual data sizes and bottlenecks first. Add stable security IDs, exchange calendars, corporate actions, and point-in-time/revision contracts before trusting larger research results. Then consider partitioned immutable raw inputs, incremental keyed validation, version/catalog management, object storage, orchestration, access controls, and observable retries. Partitioning or distributing duplicate checks introduces cross-partition/global-state correctness requirements. None of those institutional extensions is presented as implemented.

### 10. How do you know the benchmark is fair?

Inputs, group keys, date ranges, null handling, sample-standard-deviation definitions, and materialized outputs match. Every workload passes a full-result pandas comparison before any timed recording. pandas uses vectorized dates and PyArrow pushdown. Setup and B/C/D preloads are excluded for both sides, while A/E include reads. Report wall and CPU separately; use fresh engine/workload processes and record RSS samples, versions, hardware, and input hashes. Acknowledge warm caches, native thread defaults, different execution models, limited repetitions, synthetic distribution, and sandbox CPU-feature notices. No 5M benchmark was executed.

## E. Exact five-minute live demonstration

Before the interview, install dependencies and run the tests so the demonstration needs no network:

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

**0:00–0:40 — Help and the complete synthetic pipeline.**

```bash
uv run research-data --help
uv run research-data demo
```

Expected: five commands; a SYNTHETIC label and approximate weekday calendar; 65,201 input rows, 65,194 valid rows, 7 quarantine rows; errors/warnings; a SQL security summary; printed artifact paths.

**0:40–1:30 — Show auditable invalid records.**

```bash
uv run python - <<'PY'
import json
import polars as pl
from research_data_engine import read_snapshot
s = read_snapshot("data/processed/equity_prices")
r = json.loads(s.report_path.read_text())
print("Errors:", r["errors_by_category"])
print("Warnings:", r["warning_counts"])
print(pl.read_parquet(s.directory / "quarantine.parquet")
      .select("symbol", "date", "_source_row", "_errors", "_parse_errors"))
PY
```

Expected: both duplicate rows retained in quarantine; a malformed date distinguished from a missing symbol; positive/negative financial checks; warnings on clean observations. Explain why a large movement is not automatically a bad record.

**1:30–2:15 — Query stored analytics.**

```bash
uv run research-data query --sql examples/security_summary.sql --limit 5
uv run research-data query --sql examples/rolling_volatility.sql --limit 5
```

Expected: DuckDB SQL results returned as Polars; groups include source; trailing volatility is available in 2025 because it was computed before filtering. Explain price returns versus total returns and full-window minimums.

**2:15–3:00 — Demonstrate safe reruns.**

```bash
uv run research-data ingest --config configs/prices.yaml
uv run research-data validate --dataset prices
uv run python - <<'PY'
from research_data_engine import QueryEngine
with QueryEngine() as q:
    print(q.query("SELECT count(*) AS active_rows FROM prices"))
PY
```

Expected: active row count remains **65,194**, with a new snapshot rather than appended observations. Stored-snapshot validation has no hard errors. Explain the failure-injection test proving an unsuccessful manifest publication preserves the previous snapshot.

**3:00–4:15 — Benchmark evidence and boundaries.**

```bash
uv run research-data benchmark --rows 100000 --repetitions 3
```

Expected: correctness gates first, then actual timings and memory reports for all five workloads. Numbers will vary. If time is tight, show `benchmarks/results/measured-1000000.md` from the delivered run instead. State that the 1M recorded results favor Polars/DuckDB in these particular workloads, that pandas was given vectorized dates/pushdown, and that sampled RSS is not precise allocation accounting. No 5M claim.

**4:15–5:00 — Public API and optimized plan.**

```bash
uv run python examples/research_example.py
```

Expected: two-symbol synthetic price-return slice, an optimized Polars Parquet plan, and a DuckDB grouped summary. Close with one concrete next step: exchange-calendar and adjusted-price contracts before expanding research usage.

## F. Honest limitations and preparation

Implemented: CLI/API, deterministic generation, normalization, validation/rejection/quarantine, trailing analytics, snapshots/reports, DuckDB SQL, tests, scoped measured benchmarks, and CI workflow configuration. The hosted CI workflow has not run until this repository is pushed to GitHub.

Not implemented: live feeds, real exchange calendars, corporate actions/total returns, stable security IDs, point-in-time fundamentals, revision-aware backtesting, concurrent-writer coordination, automatic snapshot retention, cloud storage, production orchestration, or a hostile-SQL resource sandbox. Validation materializes data in memory. Atomic visibility is not a power-loss durability guarantee. The optional 5M benchmark is unexecuted.

Recommended rehearsal: run the exact commands in order; inspect one rejection/quarantine test and the independent volatility reference; explain why date filtering must preserve lag context; read the 1M report's CPU/RSS columns as well as speedups. If a feature is only in the roadmap, say so.
