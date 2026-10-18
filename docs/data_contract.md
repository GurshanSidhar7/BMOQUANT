# Price data contract and configuration

## Canonical schema

| Column | Polars / Parquet logical type | Required invariant |
|---|---|---|
| `symbol` | String | Nonempty, trimmed, uppercase after CSV normalization |
| `date` | Date | Parseable using the configured format |
| `open`, `high`, `low`, `close` | Float64 | Finite and strictly positive |
| `volume` | Int64 | Nonnegative whole shares/units; zero is allowed |
| `source` | String | Nonempty, trimmed; case retained |

The unique key is **(symbol, date, source)**. Every duplicate member is an error, including identical repeated rows. Different sources remain independent for duplicate detection, returns, rolling windows, and SQL grouping. This MVP has no source-priority reconciliation or security master. Symbols can change or be reused in real data.

CSV headers are trimmed, lowercased, and runs of non-alphanumeric characters become underscores. `Trade Date` therefore maps to `trade_date`. Collisions fail. Mapping direction is canonical name → incoming name. All seven price/volume fields must be mapped; unknown canonical mappings fail. Extra incoming columns are ignored. A canonical incoming `source` is automatically preserved; `schema.source` maps a differently named source field. Otherwise `input.source` supplies a label. Never label real data `synthetic_weekdays`; change the supplied demo configuration for your own inputs.

Fields are initially scanned as strings so the first file or first rows cannot change type inference. Whitespace-only fields become null. Dates use exact configured parsing. Numeric prices accept Float64 representations; `NaN` and infinities are subsequently financial errors. Volumes require integer text within signed 64-bit range: `10.5`, `1e3`, and `100.0` are parse errors, never truncated. Malformed nonempty fields are distinct from originally missing fields.

## Configuration reference

Paths in YAML resolve relative to the **YAML file**, not the shell's current directory. Programmatically constructed `PipelineConfig` paths follow normal Python path semantics. Unknown fields and unsupported formats/policies fail early.

| Setting | Default / meaning |
|---|---|
| `dataset` | Required identifier, starting with a letter; letters/digits/underscore/hyphen |
| `input.path` | Required CSV path or directory recursively containing CSVs, including `.CSV` |
| `input.format` | `csv`, the only implemented input format |
| `input.source` | `user_csv`; used only without an incoming source mapping/column |
| `input.date_format` | `%Y-%m-%d`; Polars/Chrono date parsing format |
| `schema` | Defaults to canonical seven required names; specify every required name when overriding |
| `validation.duplicate_policy` | `quarantine` |
| `validation.invalid_price_policy` | `quarantine`; applies to all financial invariants, including volume/OHLC/overflow |
| `validation.missing_value_policy` | `reject`; bundled demo explicitly sets `quarantine` |
| `validation.malformed_value_policy` | `quarantine` |
| `validation.extreme_return_threshold` | `0.25`; absolute simple price return strictly above this value warns |
| `validation.volume_change_ratio` | `10.0`; must exceed one; both upward and downward changes warn |
| `validation.stale_price_window` | `5`; at least two consecutive unchanged-close observations |
| `validation.calendar` | `none` or `weekdays`; weekday approximation, not an exchange calendar |
| `output.path` | Required managed snapshot directory |
| `output.format` | `parquet`, the only output format |

See [validation rules](validation_rules.md) for exact policy and warning semantics. See [the runnable configuration](../configs/prices.yaml); it intentionally identifies the bundled observations as synthetic.

For a real external OHLCV CSV, copy the config, set its input path/source/mappings/date format, and select `calendar: none` unless weekday approximation is suitable. No API keys, downloads, or live-data feeds are required or implemented.

## Stored analytical columns

| Column | Definition |
|---|---|
| `simple_return` | `close / previous_retained_close - 1` |
| `log_return` | `ln(close) - ln(previous_retained_close)`; avoids ratio overflow in the log calculation |
| `realized_vol_20`, `realized_vol_30` | Sample standard deviation of the last 20/30 log returns × `sqrt(252)` |
| `average_volume_20` | Mean of the last 20 observed volumes, including the current observation |
| `dollar_volume` | `close * volume`; approximate notional in the price's currency |

All are Float64. Returns start with null independently for each symbol/source. Volatility requires all 20/30 returns, hence 21/31 prices; `ddof=1`. Average volume requires 20 volumes. Windows include today and past retained observations, never future observations. The 252 annualization factor is a convention, not a claim about an exact exchange calendar.

Rows sort by symbol, source, date. Quarantined rows never enter analytics. Returns across an absent or quarantined session span the gap; they are not necessarily one-session returns. Missing observations are neither inserted nor interpolated. Weekday warnings identify internal gaps where configured. No prices are filled with zero. Date-filtered API/SQL slices read analytics calculated on the full stored history, preserving the pre-start lag and rolling window. Recomputing returns after filtering would change the first return and can change rolling results.

These are **price returns**, not total shareholder returns. Synthetic prices and user-supplied unadjusted OHLCV have no split, dividend, currency, or corporate-action adjustment. A legitimate split may produce an extreme-return warning. Do not use this sample as investment evidence.

## Audit columns

Clean files retain `_source_file`, `_source_row`, `_warnings: List[String]`, and `_missing_sessions: Int64`. `_source_row` counts logical CSV records with the header as row 1; multiline quoted records mean it may differ from a physical line number. In-memory validation uses `<memory>` and record numbers starting at one.

Quarantine includes the canonical fields, `_source_file`, `_source_row`, `_raw_record` (JSON of mapped raw fields), `_parse_errors` (field names), and `_errors` (category codes). Canonical fields may be null or invalid there. Unmapped vendor columns are not retained. Reports count null values after normalization, including nulls resulting from parsing; error categories distinguish the cause.
