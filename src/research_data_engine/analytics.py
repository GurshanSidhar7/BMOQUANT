"""Trailing observation-window price analytics, independent for each symbol/source."""

import math

import polars as pl

from research_data_engine.transformations import GROUPS, SORT_ORDER

ANALYTIC_COLUMNS = [
    "simple_return",
    "log_return",
    "realized_vol_20",
    "realized_vol_30",
    "average_volume_20",
    "dollar_volume",
]


def with_returns(frame: pl.LazyFrame) -> pl.LazyFrame:
    """First observation is null. Prices must already be positive and finite."""
    previous = pl.col("close").shift(1).over(GROUPS)
    return frame.sort(SORT_ORDER).with_columns(
        (pl.col("close") / previous - 1).alias("simple_return"),
        (pl.col("close").log() - previous.log()).alias("log_return"),
    )


def calculate_analytics(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Sample volatility (ddof=1), 252 annualization, full trailing windows only.

    Twenty log returns require 21 prices. Missing sessions are never interpolated.
    Dollar volume is close * volume, an approximation to traded notional.
    """
    return with_returns(frame).with_columns(
        *[
            (
                pl.col("log_return").rolling_std(w, min_samples=w, ddof=1).over(GROUPS)
                * math.sqrt(252)
            ).alias(f"realized_vol_{w}")
            for w in (20, 30)
        ],
        pl.col("volume").rolling_mean(20, min_samples=20).over(GROUPS).alias("average_volume_20"),
        (pl.col("close") * pl.col("volume")).alias("dollar_volume"),
    )
