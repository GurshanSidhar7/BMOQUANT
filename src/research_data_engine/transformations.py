"""Canonical schema normalization, expressed as a lazy Polars query."""

import polars as pl

from research_data_engine.config import CANONICAL_COLUMNS, PipelineConfig, normalize_name
from research_data_engine.exceptions import IngestionError

PRICE_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
    "source": pl.String,
}
KEY = ["symbol", "date", "source"]
GROUPS = ["symbol", "source"]
SORT_ORDER = ["symbol", "source", "date"]
PRICES = ["open", "high", "low", "close"]


def normalize_prices(frame: pl.LazyFrame, config: PipelineConfig) -> pl.LazyFrame:
    """Preserve raw mapped fields and parse failures for quarantine diagnostics."""
    names = frame.collect_schema().names()
    renames = {name: normalize_name(name) for name in names if not name.startswith("_source_")}
    if len(set(renames.values())) != len(renames):
        raise IngestionError("Input column names collide after normalization")
    if any(name.startswith("_") for name in renames.values()):
        raise IngestionError("Input uses a reserved provenance column")
    mapping = {canonical: normalize_name(raw) for canonical, raw in config.schema_mapping.items()}
    if "source" not in mapping and "source" in renames.values():
        if "source" in mapping.values():
            raise IngestionError(
                "Map schema.source explicitly; the incoming source column is ambiguous"
            )
        mapping["source"] = "source"
    missing = set(mapping.values()) - set(renames.values())
    if missing:
        raise IngestionError(f"Mapped input columns not found: {sorted(missing)}; found {names}")
    frame = frame.rename(renames).select(
        [
            pl.col(raw).cast(pl.String).str.strip_chars().replace("", None).alias(canonical)
            for canonical, raw in mapping.items()
        ]
        + [pl.col("_source_file"), pl.col("_source_row")]
    )
    if "source" not in mapping:
        frame = frame.with_columns(pl.lit(config.input.source.strip()).alias("source"))
    frame = frame.with_columns(
        pl.struct(CANONICAL_COLUMNS).struct.json_encode().alias("_raw_record")
    )
    conversions = {
        "date": pl.col("date").str.strptime(pl.Date, format=config.input.date_format, strict=False),
        **{c: pl.col(c).cast(pl.Float64, strict=False) for c in PRICES},
        "volume": pl.col("volume").cast(pl.Int64, strict=False),
    }
    frame = frame.with_columns(
        pl.concat_list(
            [
                pl.when(pl.col(name).is_not_null() & expr.is_null())
                .then(pl.lit(name))
                .otherwise(None)
                for name, expr in conversions.items()
            ]
        )
        .list.drop_nulls()
        .alias("_parse_errors"),
        pl.col("symbol").str.to_uppercase(),
        *[expr.alias(name) for name, expr in conversions.items()],
        pl.col("_source_row").cast(pl.Int64),
    )
    return frame
