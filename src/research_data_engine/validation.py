"""Financial invariants are errors; unusual but possible observations are warnings."""

from collections import Counter
from dataclasses import dataclass

import numpy as np
import polars as pl

from research_data_engine.analytics import ANALYTIC_COLUMNS, calculate_analytics
from research_data_engine.config import CANONICAL_COLUMNS, ValidationConfig
from research_data_engine.exceptions import DataValidationError
from research_data_engine.transformations import GROUPS, KEY, PRICE_SCHEMA, PRICES


@dataclass
class ValidationResult:
    clean: pl.DataFrame
    quarantine: pl.DataFrame
    errors: dict[str, int]
    warnings: dict[str, int]
    missing_values: dict[str, int]
    rejected_categories: list[str]
    input_rows: int

    @property
    def rejected(self) -> bool:
        return bool(self.rejected_categories)


def _codes(conditions: dict[str, pl.Expr]) -> pl.Expr:
    return pl.concat_list(
        [
            pl.when(condition.fill_null(False)).then(pl.lit(name)).otherwise(None)
            for name, condition in conditions.items()
        ]
    ).list.drop_nulls()


def _counts(frame: pl.DataFrame, column: str) -> dict[str, int]:
    return dict(
        sorted(Counter(frame[column].explode(empty_as_null=True).drop_nulls().to_list()).items())
    )


def _add_warnings(frame: pl.DataFrame, config: ValidationConfig) -> pl.DataFrame:
    previous_volume = pl.col("volume").shift(1).over(GROUPS)
    frame = frame.with_columns(
        (pl.col("close") != pl.col("close").shift(1).over(GROUPS))
        .fill_null(True)
        .cast(pl.Int64)
        .alias("_price_change"),
        previous_volume.alias("_previous_volume"),
    ).with_columns(pl.col("_price_change").cum_sum().over(GROUPS).alias("_stale_group"))
    missing = np.zeros(frame.height, dtype=np.int64)
    if config.calendar == "weekdays" and frame.height:
        previous_dates = (
            frame.select(pl.col("date").shift(1).over(GROUPS).fill_null(pl.col("date")))
            .to_series()
            .to_numpy()
            .astype("datetime64[D]")
        )
        dates = frame["date"].to_numpy().astype("datetime64[D]")
        missing = np.maximum(np.busday_count(previous_dates + np.timedelta64(1, "D"), dates), 0)
    frame = frame.with_columns(pl.Series("_missing_sessions", missing))
    prev = pl.col("_previous_volume")
    return frame.with_columns(
        _codes(
            {
                "extreme_return": pl.col("simple_return").abs() > config.extreme_return_threshold,
                "volume_change": ((prev == 0) & (pl.col("volume") > 0))
                | (pl.col("volume") > prev * config.volume_change_ratio)
                | ((prev > 0) & (pl.col("volume") < prev / config.volume_change_ratio)),
                "stale_price": pl.col("close").cum_count().over([*GROUPS, "_stale_group"])
                >= config.stale_price_window,
                "missing_expected_sessions": pl.col("_missing_sessions") > 0,
            }
        ).alias("_warnings")
    ).drop("_price_change", "_previous_volume", "_stale_group")


def validate_prices(
    frame: pl.DataFrame, config: ValidationConfig | None = None
) -> ValidationResult:
    """Quarantine every member of a duplicate group; never silently choose a winner.

    Validation materializes one normalized dataset. Global duplicate detection, sorted
    analytics, and record-level reports are deliberate MVP memory boundaries.
    """
    config = config or ValidationConfig()
    wrong = {
        c: str(frame.schema.get(c))
        for c, dtype in PRICE_SCHEMA.items()
        if frame.schema.get(c) != dtype
    }
    if wrong:
        raise DataValidationError(f"Canonical columns are missing or have incorrect types: {wrong}")
    missing_values = {c: frame[c].null_count() for c in CANONICAL_COLUMNS}
    if "_source_file" not in frame.columns:
        frame = frame.with_columns(pl.lit("<memory>").alias("_source_file"))
    if "_source_row" not in frame.columns:
        frame = frame.with_row_index("_source_row", offset=1).with_columns(
            pl.col("_source_row").cast(pl.Int64)
        )
    if "_parse_errors" not in frame.columns:
        frame = frame.with_columns(pl.lit([], dtype=pl.List(pl.String)).alias("_parse_errors"))
    if "_raw_record" not in frame.columns:
        frame = frame.with_columns(
            pl.struct(CANONICAL_COLUMNS).struct.json_encode().alias("_raw_record")
        )
    nonfinite_returns = [
        pl.col(c).is_not_null() & ~pl.col(c).is_finite()
        for c in ("simple_return", "log_return")
        if c in frame.columns
    ]
    conditions = {
        "missing_value": pl.any_horizontal(
            pl.col(c).is_null() & ~pl.col("_parse_errors").list.contains(c)
            for c in CANONICAL_COLUMNS
        )
        | (pl.col("symbol").str.strip_chars() == "")
        | (pl.col("source").str.strip_chars() == ""),
        "malformed_value": pl.col("_parse_errors").list.len() > 0,
        "duplicate_key": (pl.len().over(KEY) > 1)
        & pl.all_horizontal(pl.col(c).is_not_null() for c in KEY),
        "invalid_price": pl.any_horizontal(pl.col(c) <= 0 for c in PRICES),
        "nonfinite_price": pl.any_horizontal(~pl.col(c).is_finite() for c in PRICES),
        "negative_volume": pl.col("volume") < 0,
        "invalid_ohlc": (pl.col("high") < pl.max_horizontal("open", "close", "low"))
        | (pl.col("low") > pl.min_horizontal("open", "close", "high")),
        "nonfinite_return": pl.any_horizontal(nonfinite_returns)
        if nonfinite_returns
        else pl.lit(False),
    }
    # Recompute derived columns rather than trusting a stale caller-provided calculation.
    frame = frame.with_columns(_codes(conditions).alias("_errors")).drop(
        *[c for c in [*ANALYTIC_COLUMNS, "_warnings", "_missing_sessions"] if c in frame.columns]
    )
    bad = frame.filter(pl.col("_errors").list.len() > 0)
    clean = frame.filter(pl.col("_errors").list.len() == 0)
    # Finite positive prices can still overflow a ratio or dollar-volume product.
    # Recompute after quarantine so all retained returns use the prior retained observation.
    while True:
        computed = calculate_analytics(clean.lazy()).collect()
        overflow = computed.with_columns(
            _codes(
                {
                    "nonfinite_return": pl.any_horizontal(
                        pl.col(c).is_not_null() & ~pl.col(c).is_finite()
                        for c in ("simple_return", "log_return")
                    ),
                    "nonfinite_analytics": pl.any_horizontal(
                        pl.col(c).is_not_null() & ~pl.col(c).is_finite()
                        for c in ANALYTIC_COLUMNS
                        if c not in ("simple_return", "log_return")
                    ),
                }
            ).alias("_computed_errors")
        )
        invalid = overflow.filter(pl.col("_computed_errors").list.len() > 0)
        if invalid.is_empty():
            clean = computed
            break
        new_bad = invalid.select(frame.columns).with_columns(
            invalid["_computed_errors"].alias("_errors")
        )
        bad = pl.concat([bad, new_bad], how="vertical")
        clean = overflow.filter(pl.col("_computed_errors").list.len() == 0).select(frame.columns)
    errors = _counts(bad, "_errors")
    rejected = [category for category in errors if config.policy_for(category) == "reject"]
    if frame.is_empty() or clean.is_empty():
        errors["empty_dataset"] = 1
        rejected.append("empty_dataset")
    clean = _add_warnings(clean, config)
    warnings = _counts(clean, "_warnings")
    clean = clean.drop("_errors", "_parse_errors", "_raw_record")
    return ValidationResult(
        clean=clean,
        quarantine=bad.sort(["_source_file", "_source_row"]),
        errors=errors,
        warnings=warnings,
        missing_values=missing_values,
        rejected_categories=sorted(rejected),
        input_rows=frame.height,
    )
