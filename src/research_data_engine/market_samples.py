"""Small, frozen historical examples with explicit equity and spot-price contracts.

Downloads are an optional preparation step. Tests, the pipeline, and the website
use checked-in CSV snapshots and never require a live provider connection.
"""

import hashlib
import html
import json
import math
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from research_data_engine.analytics import calculate_price_analytics
from research_data_engine.exceptions import DataValidationError

START = date(2025, 2, 24)
END = date(2025, 12, 31)
EIA_URL = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RWTC&f=D"
EIA_PAGE = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=RWTC&f=D"


def yahoo_url(symbol: str) -> str:
    if symbol not in ("NVDA", "SNDK"):
        raise ValueError("This example downloader supports NVDA and SNDK only")
    begin = int(datetime.combine(START, datetime.min.time(), UTC).timestamp())
    finish = int(datetime.combine(END + timedelta(days=1), datetime.min.time(), UTC).timestamp())
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={begin}&period2={finish}&interval=1d"
    )


def parse_yahoo_prices(body: bytes, symbol: str) -> pl.DataFrame:
    """Preserve provider OHLCV; never substitute dividend-adjusted close for OHLC."""
    result = json.loads(body)["chart"]["result"][0]
    metadata = result["meta"]
    if metadata["symbol"] != symbol or metadata["currency"] != "USD":
        raise DataValidationError("Unexpected provider symbol or currency")
    if metadata["instrumentType"] != "EQUITY":
        raise DataValidationError("Expected an equity OHLCV sample")
    quote = result["indicators"]["quote"][0]
    fields = ("open", "high", "low", "close", "volume")
    timestamps = result["timestamp"]
    if not timestamps or any(len(quote[field]) != len(timestamps) for field in fields):
        raise DataValidationError("Missing or mismatched provider observations")
    rows = []
    for index, timestamp in enumerate(timestamps):
        observed = datetime.fromtimestamp(
            timestamp, ZoneInfo(metadata["exchangeTimezoneName"])
        ).date()
        if START <= observed <= END:
            rows.append(
                {
                    "symbol": symbol,
                    "date": observed,
                    **{field: quote[field][index] for field in fields},
                    "source": "yahoo_finance",
                }
            )
    return pl.DataFrame(rows, schema_overrides={"volume": pl.Int64}).sort("date")


def parse_eia_spot(body: bytes) -> pl.DataFrame:
    """Read EIA's Monday–Friday table, including weeks crossing a year boundary.

    Blank cells are unpublished observations, not zero prices. Preserve their
    absence; only observed daily prices belong in the resulting snapshot.
    """
    text = body.decode("utf-8")
    rows = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, flags=re.I | re.S):
        label = re.search(r"<td[^>]*class=['\"]B6['\"][^>]*>(.*?)</td>", row, re.I | re.S)
        if not label:
            continue
        label_text = html.unescape(re.sub(r"<[^>]+>", "", label[1])).strip()
        match = re.match(r"(\d{4})\s+([A-Za-z]{3})-\s*(\d{1,2})\s+to\b", label_text)
        if not match:
            raise DataValidationError(f"Unrecognized EIA week label: {label_text}")
        monday = datetime.strptime(" ".join(match.groups()), "%Y %b %d").date()
        cells = re.findall(r"<td[^>]*class=['\"]B3['\"][^>]*>(.*?)</td>", row, re.I | re.S)
        if len(cells) != 5 or monday.weekday() != 0:
            raise DataValidationError("EIA daily table no longer has five Monday–Friday cells")
        for offset, cell in enumerate(cells):
            observed = monday + timedelta(days=offset)
            value = html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()
            if START <= observed <= END and value:
                rows.append(
                    {
                        "symbol": "WTI",
                        "date": observed,
                        "close": float(value),
                        "source": "eia_wti_spot",
                    }
                )
    if not rows:
        raise DataValidationError("No EIA daily observations found for the sample window")
    return pl.DataFrame(rows).sort("date")


def load_spot_prices(path: Path) -> pl.DataFrame:
    """Validate a positive-price spot sample and reuse the equity price mathematics.

    This is a price-only contract. There are no invented open/high/low/volume
    values. Signed commodity prices require another return definition and are
    deliberately unsupported by this small historical example.
    """
    try:
        frame = pl.read_csv(path, try_parse_dates=True, schema_overrides={"close": pl.Float64})
        if frame.columns != ["symbol", "date", "close", "source"]:
            raise DataValidationError("Spot CSV requires symbol,date,close,source only")
        if frame.schema["date"] != pl.Date or frame.is_empty():
            raise DataValidationError("Spot sample requires dates and at least one observation")
        if sum(frame.null_count().row(0)) or frame.is_duplicated().any():
            raise DataValidationError("Missing or duplicate spot observations")
        if frame.select(pl.struct("symbol", "date", "source").is_duplicated().any()).item():
            raise DataValidationError("Duplicate spot observation key")
        if frame.filter((pl.col("close") <= 0) | ~pl.col("close").is_finite()).height:
            raise DataValidationError("Spot sample requires positive finite prices")
        if frame["symbol"].unique().to_list() != ["WTI"] or frame["source"].unique().to_list() != [
            "eia_wti_spot"
        ]:
            raise DataValidationError("Unexpected spot instrument or source")
        frame = frame.with_row_index("_source_row", offset=2)
        computed = calculate_price_analytics(frame.lazy()).collect()
        if any(
            not math.isfinite(value)
            for column in ("simple_return", "log_return", "realized_vol_20", "realized_vol_30")
            for value in computed[column].drop_nulls()
        ):
            raise DataValidationError("Spot analytics exceed the supported numeric range")
        return computed.with_columns(
            pl.when(pl.col("simple_return").abs() > 0.25)
            .then(pl.lit(["extreme_return"]))
            .otherwise(pl.lit([], dtype=pl.List(pl.String)))
            .alias("_warnings"),
        )
    except (OSError, pl.exceptions.PolarsError) as exc:
        raise DataValidationError(f"Cannot read spot sample: {exc}") from exc


def verified_manifest(directory: Path) -> dict:
    """Refuse stale, missing, or edited snapshots before exporting them to the UI."""
    manifest = json.loads((directory / "manifest.json").read_text())
    if {sample["symbol"] for sample in manifest["samples"]} != {"NVDA", "SNDK", "WTI"}:
        raise DataValidationError("Expected exactly NVDA, SNDK, and WTI samples")
    for sample in manifest["samples"]:
        path = directory / sample["path"]
        if directory.resolve() not in path.resolve().parents:
            raise DataValidationError("Market snapshot path escapes its directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sample["sha256"]:
            raise DataValidationError(f"Market snapshot checksum mismatch: {sample['symbol']}")
        if pl.read_csv(path).height != sample["rows"]:
            raise DataValidationError(f"Market snapshot row count mismatch: {sample['symbol']}")
    return manifest
