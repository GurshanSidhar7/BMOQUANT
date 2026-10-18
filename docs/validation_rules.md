# Validation and policy semantics

Validation separates **errors**, which violate the contract, from **warnings**, which may be legitimate market behavior. No rule silently drops a record.

## Structural failures

Missing files, missing mapped columns, colliding normalized headers, malformed CSV structure, and wrong canonical dtypes raise actionable exceptions. A header-only or entirely invalid dataset is rejected with an `empty_dataset` report; it cannot replace a prior valid snapshot. Empty input directories fail discovery. Unparseable nonempty dates/numbers become `malformed_value` row errors, with raw values retained. Real missing values use `missing_value` instead, so a malformed date's policy does not accidentally invoke the missing-value policy.

## Row error categories

| Category | Check | Policy setting |
|---|---|---|
| `missing_value` | Any canonical value missing, blank symbol/source | `missing_value_policy` |
| `malformed_value` | Nonempty date/numeric text could not be cast | `malformed_value_policy` |
| `duplicate_key` | More than one row with (symbol, date, source), across all input files | `duplicate_policy` |
| `invalid_price` | Any OHLC value ≤ 0 | `invalid_price_policy` |
| `nonfinite_price` | NaN / positive or negative infinity in any OHLC value | `invalid_price_policy` |
| `negative_volume` | Volume < 0 | `invalid_price_policy` |
| `invalid_ohlc` | High below open/close/low, or low above open/close/high | `invalid_price_policy` |
| `nonfinite_return` | Non-finite caller-supplied simple/log return | `invalid_price_policy` |

Null first returns and insufficient-history rolling values are expected, not errors. A row can violate several categories; category totals can exceed quarantined row totals. Every row is counted exactly once in either clean or quarantine. `empty_dataset` is a dataset-level error count of one, not an extra quarantined record.

Duplicate detection requires all key fields to be non-null: two unknown/unparseable dates do not establish a shared observation date. Their parse/missing policies apply instead.

Only two policy values exist:

- **`quarantine`:** Remove all offending rows from the clean candidate, retain them with reasons, publish remaining valid observations. All members of a duplicate group are quarantined; no arbitrary first/last selection.
- **`reject`:** Reject the entire run if any category using this policy occurs. Save a rejected report and quarantine artifacts, raise a nonzero CLI error, preserve the active snapshot. Even otherwise valid rows in that run are not published.

When a row has multiple categories, any applicable `reject` takes precedence for the entire run. There is no implicit dropping, deduplication, imputation, or partial publication after rejection. If no valid rows remain, rejection applies regardless of per-row settings. Structural failures before materialization do not promise row-level artifacts.

Financial validation precedes calculation. Analytics are calculated once on the retained input. If finite positive inputs nevertheless overflow derived Float64 arithmetic, the whole run stops with an actionable `DataValidationError` and example source-row references, regardless of row policies. Review the input units and prices before rerunning. The previous saved snapshot remains active. This calculation failure does not produce a new report/quarantine bundle. There is no iterative row removal or automatic repair of the price history.

## Warnings retained in clean data

| Warning | Exact semantics |
|---|---|
| `extreme_return` | `abs(simple_return) > extreme_return_threshold`; strict inequality |
| `volume_change` | Current volume > previous × ratio, or current < previous / ratio; zero → positive also warns |
| `stale_price` | Same close for at least `stale_price_window` consecutive retained observations; flags threshold row and subsequent stale rows |
| `missing_expected_sessions` | At least one weekday strictly between adjacent retained dates when `calendar: weekdays` |

All lags and consecutive counts group by symbol **and source**, and use only past/current observations. Zero → zero volume is not a change. Positive → zero is a large downward change. Stale prices compare exact input Float64 closes; there is no fuzzy tick-size matching. Warnings never trigger quarantine or rejection. The report counts warned observations per category, and separately sums `_missing_sessions` into `missing_session_count`.

**No exchange calendar is bundled.** `weekdays` is an approximation appropriate for the synthetic generator; it treats weekday holidays as expected sessions and cannot distinguish suspensions, listings, delistings, or genuine vendor gaps. `none` disables gap warnings. Gaps are checked only inside each observed span, not before the first or after the last observation. Quarantining a row can create an internal gap. These limits are explicit rather than presenting a business-day calendar as an exchange calendar.

## Example audit

`research-data demo` creates 65,200 synthetic observations, injects five erroneous rows, and appends a duplicate of an existing row. The duplicate **pair** is quarantined, yielding 65,201 input rows, 7 quarantined records, and 65,194 valid records. The supplied errors cover a missing symbol, unparseable date, negative volume, negative close, non-finite close, and duplicate key. An extreme price movement and a volume spike remain in the clean output with warnings.

Inspect the active report and quarantine through the manifest rather than hardcoding a run ID:

```python
import json
import polars as pl
from research_data_engine import read_snapshot

snapshot = read_snapshot("data/processed/equity_prices")
print(json.loads(snapshot.report_path.read_text()))
print(
    pl.read_parquet(snapshot.directory / "quarantine.parquet").select(
        "_source_file", "_source_row", "_errors", "_parse_errors", "_raw_record"
    )
)
```
