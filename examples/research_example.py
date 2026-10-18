"""Run `research-data demo` first. All demo observations are SYNTHETIC."""

from datetime import date

import polars as pl

from research_data_engine import QueryEngine, load_prices, read_snapshot

prices = load_prices(symbols=["SYN0000", "SYN0001"], start="2025-01-01", end="2025-12-31")
print("SYNTHETIC price analytics:")
print(prices.select("symbol", "source", "date", "simple_return", "realized_vol_20").head())

snapshot = read_snapshot("data/processed/equity_prices")
plan = (
    pl.scan_parquet(snapshot.prices_path)
    .filter(pl.col("date") >= date(2025, 1, 1))
    .select("symbol", "source", "volume")
    .group_by("symbol", "source")
    .agg(pl.col("volume").mean().alias("average_volume"))
)
print("Optimized Polars plan (projection and predicate pushdown):")
print(plan.explain(optimized=True))
print(plan.collect())

with QueryEngine() as engine:
    print(
        engine.query("""
        SELECT symbol, source, avg(simple_return) AS average_price_return
        FROM prices GROUP BY symbol, source ORDER BY average_price_return DESC LIMIT 5
    """)
    )
