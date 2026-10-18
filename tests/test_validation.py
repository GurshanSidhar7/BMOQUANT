from datetime import date

import polars as pl
import pytest
from conftest import make_prices

from research_data_engine import ValidationConfig, validate_prices
from research_data_engine.exceptions import DataValidationError


def test_duplicates_quarantine_every_member_and_sources_stay_separate():
    one = make_prices([100.0])
    other_source = one.with_columns(pl.lit("other").alias("source"))
    result = validate_prices(pl.concat([one, one, other_source]))
    assert result.errors == {"duplicate_key": 2}
    assert result.clean.height == 1
    assert result.clean["source"][0] == "other"
    assert result.input_rows == result.clean.height + result.quarantine.height


@pytest.mark.parametrize(
    ("column", "value", "category"),
    [
        ("volume", -1, "negative_volume"),
        ("open", 0.0, "invalid_price"),
        ("high", -1.0, "invalid_price"),
        ("low", 0.0, "invalid_price"),
        ("close", -10.0, "invalid_price"),
        ("high", 90.0, "invalid_ohlc"),
        ("low", 110.0, "invalid_ohlc"),
        ("close", float("nan"), "nonfinite_price"),
        ("open", float("inf"), "nonfinite_price"),
        ("close", None, "missing_value"),
        ("symbol", None, "missing_value"),
        ("symbol", "  ", "missing_value"),
    ],
)
def test_financial_and_missing_value_errors(column, value, category):
    frame = make_prices([100.0, 101.0])
    dtype = frame.schema[column]
    frame = frame.with_columns(pl.Series(column, [value, frame[column][1]], dtype=dtype))
    result = validate_prices(frame, ValidationConfig(missing_value_policy="quarantine"))
    assert result.errors[category] == 1
    assert result.quarantine.height == 1
    assert result.clean.height == 1


def test_reject_policy_is_explicit():
    frame = make_prices([100.0, 101.0]).with_columns(pl.Series("volume", [-1, 100]))
    result = validate_prices(frame, ValidationConfig(invalid_price_policy="reject"))
    assert result.rejected_categories == ["negative_volume"]


def test_extreme_price_move_is_warning_and_kept():
    result = validate_prices(make_prices([100.0, 200.0, 201.0]))
    assert result.clean.height == 3
    assert result.quarantine.is_empty()
    assert result.warnings["extreme_return"] == 1


def test_stale_price_warning_uses_only_history():
    config = ValidationConfig(stale_price_window=3)
    result = validate_prices(make_prices([100.0, 100.0, 100.0, 100.0, 101.0]), config)
    flags = result.clean["_warnings"].to_list()
    assert "stale_price" not in flags[0] + flags[1]
    assert "stale_price" in flags[2] and "stale_price" in flags[3]
    assert "stale_price" not in flags[4]


def test_volume_zero_and_large_changes_are_warnings():
    frame = make_prices([100.0] * 4).with_columns(pl.Series("volume", [0, 100, 10000, 0]))
    result = validate_prices(frame)
    assert result.clean.height == 4
    assert result.warnings["volume_change"] == 3


def test_missing_weekday_sessions_count_is_explicitly_approximate():
    frame = make_prices([100.0, 101.0]).with_columns(
        pl.Series("date", [date(2025, 1, 6), date(2025, 1, 8)])
    )
    result = validate_prices(frame, ValidationConfig(calendar="weekdays"))
    assert result.warnings["missing_expected_sessions"] == 1
    assert result.clean["_missing_sessions"].to_list() == [0, 1]
    assert "missing_expected_sessions" not in validate_prices(frame).warnings


@pytest.mark.parametrize("prices,volume", [([1e-308, 1e308], 0), ([1e308], 100)])
def test_numeric_overflow_stops_for_input_review(prices, volume):
    frame = make_prices(prices).with_columns(pl.lit(volume, dtype=pl.Int64).alias("volume"))
    with pytest.raises(DataValidationError, match="Review input units and prices"):
        validate_prices(frame)


def test_existing_nonfinite_returns_are_detected():
    frame = make_prices([100.0, 101.0]).with_columns(
        pl.Series("simple_return", [None, float("inf")])
    )
    assert validate_prices(frame).errors["nonfinite_return"] == 1


def test_empty_dataset_rejected(prices):
    result = validate_prices(prices.head(0))
    assert result.rejected_categories == ["empty_dataset"]


def test_incorrect_canonical_dtype_is_structural_error(prices):
    with pytest.raises(DataValidationError, match="incorrect types"):
        validate_prices(prices.with_columns(pl.col("volume").cast(pl.Float64)))
