"""Deterministic SYNTHETIC OHLCV; weekdays approximate exchange sessions."""

from pathlib import Path

import numpy as np
import polars as pl

from research_data_engine.config import InputConfig, OutputConfig, PipelineConfig, ValidationConfig


def generate_prices(*, symbols: int = 50, rows: int | None = None, seed: int = 42) -> pl.DataFrame:
    """Default: 50 synthetic securities, Jan 2021–Dec 2025 (65,200 weekday observations)."""
    if symbols < 1 or (rows is not None and rows < 1):
        raise ValueError("symbols and rows must be positive")
    sessions = (
        int(np.busday_count("2021-01-01", "2026-01-01"))
        if rows is None
        else int(np.ceil(rows / symbols))
    )
    count = sessions * symbols
    rng = np.random.default_rng(seed)
    log_changes = rng.normal(0.0002, 0.015, (symbols, sessions))
    close = (50 * np.exp(np.cumsum(log_changes, axis=1))).ravel()
    previous = np.column_stack(
        [np.full(symbols, 50), close.reshape(symbols, sessions)[:, :-1]]
    ).ravel()
    opening = previous * np.exp(rng.normal(0, 0.003, count))
    spread = rng.uniform(0.001, 0.02, count)
    dates = np.busday_offset(np.datetime64("2021-01-01"), np.arange(sessions), roll="forward")
    result = pl.DataFrame(
        {
            "symbol": np.repeat([f"SYN{i:04d}" for i in range(symbols)], sessions),
            "date": np.tile(dates, symbols),
            "open": opening,
            "high": np.maximum(opening, close) * (1 + spread),
            "low": np.minimum(opening, close) * (1 - spread),
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, count, dtype=np.int64),
            "source": np.full(count, "synthetic_weekdays"),
        }
    ).with_columns(pl.col("date").cast(pl.Date))
    return result.head(rows) if rows is not None else result


def write_sample_csv(
    path: str | Path,
    *,
    dirty: bool = False,
    symbols: int = 50,
    rows: int | None = None,
    seed: int = 42,
) -> Path:
    """Optionally inject documented errors plus a legitimate extreme movement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = generate_prices(symbols=symbols, rows=rows, seed=seed).with_columns(
        pl.col("date").dt.strftime("%Y-%m-%d")
    )
    if dirty:
        if frame.height < 12:
            raise ValueError("Dirty example needs at least 12 rows")
        frame = (
            frame.with_row_index("_i")
            .with_columns(
                pl.when(pl.col("_i") == 0).then(None).otherwise(pl.col("symbol")).alias("symbol"),
                pl.when(pl.col("_i") == 1)
                .then(pl.lit("not-a-date"))
                .otherwise(pl.col("date"))
                .alias("date"),
                pl.when(pl.col("_i") == 2)
                .then(-10)
                .when(pl.col("_i") == 25)
                .then(pl.col("volume") * 100)
                .otherwise(pl.col("volume"))
                .alias("volume"),
                pl.when(pl.col("_i") == 3)
                .then(-1.0)
                .when(pl.col("_i") == 4)
                .then(float("nan"))
                .when(pl.col("_i") == 20)
                .then(pl.col("close") * 4)
                .otherwise(pl.col("close"))
                .alias("close"),
                pl.when(pl.col("_i") == 20)
                .then(pl.col("high") * 4)
                .otherwise(pl.col("high"))
                .alias("high"),
            )
            .drop("_i")
        )
        frame = pl.concat([frame, frame.slice(10, 1)])
    frame.rename({"symbol": "ticker", "date": "trade_date"}).write_csv(path)
    return path


def demo_config(directory: str | Path) -> PipelineConfig:
    directory = Path(directory).resolve()
    return PipelineConfig(
        dataset="equity_prices",
        input=InputConfig(
            path=directory / "raw" / "synthetic_prices.csv", source="synthetic_weekdays"
        ),
        schema={
            c: {"symbol": "ticker", "date": "trade_date"}.get(c, c)
            for c in ("symbol", "date", "open", "high", "low", "close", "volume")
        },
        validation=ValidationConfig(missing_value_policy="quarantine", calendar="weekdays"),
        output=OutputConfig(path=directory / "processed" / "equity_prices"),
    )
