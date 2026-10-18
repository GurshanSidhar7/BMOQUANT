from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from research_data_engine.sample_data import demo_config, generate_prices


def make_prices(
    closes: list[float], *, symbol: str = "AAA", source: str = "fixture"
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": [symbol] * len(closes),
            "date": [date(2025, 1, 1) + timedelta(days=i) for i in range(len(closes))],
            "open": closes,
            "high": [v * 1.05 for v in closes],
            "low": [v * 0.95 for v in closes],
            "close": closes,
            "volume": [100] * len(closes),
            "source": [source] * len(closes),
        },
        schema_overrides={
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Int64,
        },
    )


@pytest.fixture
def prices() -> pl.DataFrame:
    return generate_prices(symbols=2, rows=100)


@pytest.fixture
def config(tmp_path: Path, prices: pl.DataFrame):
    settings = demo_config(tmp_path)
    settings.input.path.parent.mkdir(parents=True)
    prices.rename({"symbol": "ticker", "date": "trade_date"}).write_csv(settings.input.path)
    return settings
