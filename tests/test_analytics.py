import math

import numpy as np
import polars as pl
import pytest
from conftest import make_prices

from research_data_engine import calculate_analytics


def test_simple_and_log_return_definitions():
    result = calculate_analytics(make_prices([100.0, 110.0, 99.0]).lazy()).collect()
    assert result["simple_return"][0] is None
    assert result["simple_return"].tail(2).to_list() == pytest.approx([0.1, -0.1])
    assert result["log_return"].tail(2).to_list() == pytest.approx([math.log(1.1), math.log(0.9)])
    assert result["dollar_volume"].to_list() == [10000.0, 11000.0, 9900.0]


def test_rolling_volatility_matches_independent_numpy_reference(prices):
    result = calculate_analytics(prices.lazy()).collect()
    for group in result.partition_by(["symbol", "source"]):
        log_returns = np.diff(np.log(group["close"].to_numpy()))
        for window in (20, 30):
            actual = group[f"realized_vol_{window}"]
            assert actual.head(window).null_count() == window
            expected = [
                np.std(log_returns[i - window : i], ddof=1) * np.sqrt(252)
                for i in range(window, group.height)
            ]
            assert actual.slice(window).to_list() == pytest.approx(expected, rel=1e-10, abs=1e-12)
        assert group["average_volume_20"][18] is None
        assert group["average_volume_20"][19] == pytest.approx(group["volume"].head(20).mean())


def test_symbol_and_source_boundaries():
    a = make_prices([100.0, 110.0])
    b = make_prices([1000.0, 900.0], symbol="BBB")
    other = make_prices([20.0, 40.0], source="other")
    result = calculate_analytics(pl.concat([a, b, other]).lazy()).collect()
    for frame in result.partition_by(["symbol", "source"]):
        assert frame["simple_return"][0] is None
    assert result.filter(pl.col("source") == "other")["simple_return"][1] == 1.0


def test_order_does_not_change_results(prices):
    expected = calculate_analytics(prices.lazy()).collect()
    shuffled = prices.sample(fraction=1, shuffle=True, seed=27)
    assert calculate_analytics(shuffled.lazy()).collect().equals(expected)


def test_appending_future_rows_does_not_change_history(prices):
    one = prices.filter(pl.col("symbol") == "SYN0000")
    before = calculate_analytics(one.head(35).lazy()).collect()
    after = calculate_analytics(one.lazy()).collect().head(35)
    assert before.equals(after)
