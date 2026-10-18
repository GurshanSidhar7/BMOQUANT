# Engineering decisions

This document describes the implemented MVP and explicitly separates future work. It is an independent portfolio project built around synthetic examples, not software commissioned or endorsed by an asset manager.

## 1. Polars for normalization and financial transformations

Polars makes casts, financial invariants, group boundaries, and trailing windows explicit column expressions. Its lazy engine can combine projections/predicates before scanning, and its native parallel execution can reduce elapsed time on suitable workloads. Arrow-oriented columnar interoperability avoids a Python object per numeric value and helps exchange results with DuckDB.

This does not imply that every Polars operation uses less memory or is faster. Sorting, hash grouping, retained eager frames, and multiple native threads consume memory; the benchmark measures them. The pipeline materializes a normalized frame for global validation and quarantine. It is not a streaming/out-of-core pipeline from beginning to end. pandas remains useful for small ad-hoc work, familiar indexing, richer ecosystem integrations, and a straightforward trusted benchmark baseline.

The installed-version API was checked while building: `scan_csv`, `rolling_std(min_samples=..., ddof=1)`, window grouping, optimized plans, and DuckDB-to-Polars conversion are exercised by tests and examples. The lock file, rather than a claim about every future dependency release, defines the verified environment.

## 2. DuckDB for local analytical SQL

DuckDB is embedded, queries Parquet directly, and supports grouped and windowed OLAP calculations without a service or an intermediate pandas dataset. It complements researchers who prefer SQL. `QueryEngine` resolves one immutable snapshot and creates a `prices` view; its results are Polars frames.

PostgreSQL would add service setup and data loading that this local batch workflow does not require. It would become more appropriate for concurrent transactional writes, centralized access control, managed multi-user data, or an existing organizational platform. DuckDB and this application do not replace those requirements.

User queries must start with SELECT/WITH and parse as one DuckDB SELECT statement. Extension auto-installation/loading and Python replacement scans are disabled. External access is disabled with only the resolved Parquet file allowlisted, and configuration is locked. An in-memory connection is not opened with `read_only=True` (DuckDB does not support a new read-only in-memory database); these statement/filesystem restrictions provide the equivalent local read-only query interface. This is **not a security boundary for arbitrary hostile SQL**. No CPU/memory/time sandbox or remote multi-tenant query service is implemented. DuckDB documents the [external-access and file allowlist controls](https://duckdb.org/docs/stable/operations_manual/securing_duckdb/overview).

## 3. Parquet for typed reusable outputs

Parquet preserves Date/Int64/Float64 types, compresses columnar data, and supports column projection and row-group filtering. It avoids repeatedly parsing CSV text. The app writes Zstd-compressed files and a deterministic row order. Predicate pushdown benefits depend on row-group statistics and the filter/data layout; not every filter avoids reading every row group. The explicit Python API and manifest prevent accidental reads of historical/quarantined files.

CSV stays the portable input/interchange format. Parquet is less convenient to inspect with a text editor, so CLI SQL and JSON reports make the outputs accessible. Partitioning adds little for the 65k-row demo; one clean file per snapshot avoids thousands of small files. Larger partitioned/versioned storage is future work.

## 4. Polars and DuckDB have complementary roles

Polars implements ingestion normalization, row validation, quarantine selection, and canonical financial analytics. DuckDB provides research SQL directly over the resulting Parquet snapshot. Their analytical capabilities overlap; the application does not shuttle every stage through both engines. Benchmarks use the engine suited to each stated workload and compare equivalent results.

Storing commonly used trailing analytics makes the CLI useful immediately and preserves pre-filter history. A researcher can still derive alternative windows in SQL. The cost is extra columns and the need to rerun ingestion when the core analytic definition changes. SQL examples distinguish stored calculations from query-local windows.

## 5. Reliability before throughput

All members of a duplicate key group are quarantined instead of choosing an arbitrary row. Conflicting sources are never coalesced. Extreme returns remain warnings; split-like behavior is not proof of a bad row. Returns are computed after quarantine, grouped by symbol/source, sorted by date, without interpolation or future observations. Full windows and `ddof=1` are documented and checked against an independent NumPy reference.

The pipeline publishes immutable snapshots using one atomic manifest replacement. Existing readers keep their resolved file. Repeat ingestion replaces the active logical dataset rather than appending duplicates. Retention uses disk space and needs a future pruning policy. The supported publication model is a single writer on a local filesystem, not a distributed transaction. [Architecture](architecture.md) documents filesystem and crash-durability limits.

Seeded synthetic data makes the project usable without API keys, licensing dependencies, or unreliable live endpoints. A weekday approximation keeps the MVP small but cannot identify real exchange holidays. No live performance claim, alpha result, or investment conclusion is drawn from the synthetic prices.

## What changes in a larger institutional environment? (Not implemented)

| Area | Extension and reason |
|---|---|
| Enterprise feeds | Licensed vendor adapters, source entitlement checks, ingest watermarks, retry/backfill behavior |
| Security master | Stable identifiers, exchange/currency mappings, symbol history, mergers and delistings |
| Corporate actions | Auditable split/dividend adjustments and price-versus-total-return series |
| Point-in-time fundamentals | Separate effective/as-of/availability timestamps, revision history, no restated-data leakage |
| Trading calendars | Versioned exchange sessions, time zones, half-days, suspensions and listing spans |
| Orchestration | Scheduled jobs, explicit dependencies, idempotent retries, ownership and run SLAs |
| Access control | Central identity/entitlements and storage permissions; no exposed arbitrary local SQL |
| Observability | Run metrics, failure/anomaly alerts, lineage, searchable logs and incident processes |
| Versioning and contracts | Durable dataset/catalog versions, schema evolution, automated compatibility checks |
| Historical revisions | Immutable raw snapshots and reconciliation rules, revision-aware point-in-time queries |
| Storage/compute | Larger Parquet partitions, table formats/catalogs where justified, incremental validation, distributed work only after profiling |

These extensions require new correctness contracts and operational tests. They are a roadmap, not capabilities to claim in the interview.
