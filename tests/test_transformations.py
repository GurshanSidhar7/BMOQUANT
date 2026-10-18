import polars as pl
import pytest

from research_data_engine.config import load_config
from research_data_engine.exceptions import ConfigurationError, IngestionError
from research_data_engine.ingestion import scan_prices
from research_data_engine.transformations import PRICE_SCHEMA


def test_normalizes_names_symbols_dates_and_types(config):
    raw = pl.read_csv(config.input.path).rename({"ticker": " Ticker ", "trade_date": "Trade Date"})
    raw = raw.with_columns(pl.col(" Ticker ").str.to_lowercase() + " ")
    raw.write_csv(config.input.path)
    lazy, _ = scan_prices(config)
    result = lazy.collect()
    assert {c: result.schema[c] for c in PRICE_SCHEMA} == PRICE_SCHEMA
    assert result["symbol"][0] == "SYN0000"
    assert result["date"][0].isoformat() == "2021-01-01"


def test_normalized_column_collision_fails(config):
    raw = pl.read_csv(config.input.path).with_columns(pl.col("ticker").alias(" Ticker "))
    raw.write_csv(config.input.path)
    with pytest.raises(IngestionError, match="collide"):
        scan_prices(config)


def test_config_relative_paths_and_unknown_fields(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("dataset: prices\ninput:\n  path: raw\noutput:\n  path: processed\n")
    config = load_config(path)
    assert config.input.path == tmp_path / "raw"
    assert config.output.path == tmp_path / "processed"
    path.write_text(path.read_text() + "typo: true\n")
    with pytest.raises(ConfigurationError, match="typo"):
        load_config(path)


@pytest.mark.parametrize(
    "body",
    [
        "schema: {symbol: ticker}",
        "validation: {duplicate_policy: drop}",
        "validation: {extreme_return_threshold: .nan}",
        "input: {path: raw, source: '   '}",
    ],
)
def test_invalid_configuration_is_actionable(tmp_path, body):
    path = tmp_path / "invalid.yaml"
    path.write_text("dataset: prices\ninput: {path: raw}\noutput: {path: processed}\n" + body)
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_fractional_volume_is_a_parse_error_not_truncated(config):
    raw = pl.read_csv(config.input.path).with_columns(pl.lit("10.5").alias("volume"))
    raw.write_csv(config.input.path)
    frame = scan_prices(config)[0].collect()
    assert frame["volume"].null_count() == frame.height
    assert frame["_parse_errors"][0].to_list() == ["volume"]


def test_configurable_date_format(config):
    raw = pl.read_csv(config.input.path).with_columns(
        pl.col("trade_date").str.to_date().dt.strftime("%d/%m/%Y")
    )
    raw.write_csv(config.input.path)
    config.input.date_format = "%d/%m/%Y"
    result = scan_prices(config)[0].collect()
    assert result["date"].null_count() == 0


def test_canonical_incoming_sources_are_preserved_without_explicit_mapping(config):
    raw = pl.read_csv(config.input.path).with_columns(
        pl.when(pl.col("ticker") == "SYN0000")
        .then(pl.lit("feed_a"))
        .otherwise(pl.lit("feed_b"))
        .alias("source")
    )
    raw.write_csv(config.input.path)
    result = scan_prices(config)[0].collect()
    assert set(result["source"]) == {"feed_a", "feed_b"}
