from pathlib import Path

import polars as pl
import pytest

from research_data_engine import ingest
from research_data_engine.exceptions import DataValidationError, IngestionError
from research_data_engine.ingestion import discover_csv_files, scan_prices


def test_lazy_multiple_files_are_discovered_in_order(config, prices):
    first = config.input.path.parent / "a.csv"
    second = config.input.path.parent / "z.csv"
    prices.head(30).rename({"symbol": "ticker", "date": "trade_date"}).write_csv(second)
    prices.tail(70).rename({"symbol": "ticker", "date": "trade_date"}).write_csv(first)
    config.input.path.unlink()
    config.input.path = first.parent
    lazy, files = scan_prices(config)
    assert isinstance(lazy, pl.LazyFrame)
    assert files == [first, second]
    assert lazy.collect().height == 100
    assert lazy.collect()["_source_file"][0] == str(first)
    assert lazy.collect()["_source_row"][0] == 2


def test_missing_file_and_empty_directory(tmp_path: Path):
    for path in (tmp_path, tmp_path / "missing.csv"):
        with pytest.raises(IngestionError, match="No readable CSV"):
            discover_csv_files(path)


def test_wrong_mapping_names_the_missing_column(config):
    config.schema_mapping["symbol"] = "not_a_ticker"
    with pytest.raises(IngestionError, match="not_a_ticker"):
        scan_prices(config)


@pytest.mark.parametrize("policy", ["quarantine", "reject"])
def test_malformed_date_obeys_policy(config, policy):
    raw = (
        pl.read_csv(config.input.path)
        .with_row_index("i")
        .with_columns(
            pl.when(pl.col("i") == 0)
            .then(pl.lit("bad-date"))
            .otherwise(pl.col("trade_date"))
            .alias("trade_date")
        )
        .drop("i")
    )
    raw.write_csv(config.input.path)
    config.validation.malformed_value_policy = policy
    if policy == "reject":
        with pytest.raises(DataValidationError, match="malformed_value"):
            ingest(config)
        assert not (config.output.path / "CURRENT.json").exists()
        assert list((config.output.path.parent / "rejected").glob("*/report.json"))
    else:
        run = ingest(config)
        quarantine = pl.read_parquet(run.snapshot.directory / "quarantine.parquet")
        assert quarantine.height == 1
        assert quarantine["_parse_errors"][0].to_list() == ["date"]
        assert "bad-date" in quarantine["_raw_record"][0]


def test_corrupt_csv_fails_instead_of_dropping_records(config):
    config.input.path.write_text(
        "ticker,trade_date,open,high,low,close,volume\nAAA,2025-01-01,1,2,1,2,10,extra\n"
    )
    with pytest.raises(IngestionError, match="CSV materialization failed"):
        ingest(config)


def test_malformed_value_does_not_trigger_missing_value_policy(config):
    raw = (
        pl.read_csv(config.input.path)
        .with_row_index("i")
        .with_columns(
            pl.when(pl.col("i") == 0)
            .then(pl.lit("bad-date"))
            .otherwise(pl.col("trade_date"))
            .alias("trade_date")
        )
        .drop("i")
    )
    raw.write_csv(config.input.path)
    config.validation.missing_value_policy = "reject"
    run = ingest(config)
    assert run.report["errors_by_category"] == {"malformed_value": 1}


def test_header_only_dataset_is_rejected(config):
    config.input.path.write_text("ticker,trade_date,open,high,low,close,volume\n")
    with pytest.raises(DataValidationError, match="empty_dataset"):
        ingest(config)


def test_uppercase_csv_extension_discovered(config):
    renamed = config.input.path.with_suffix(".CSV")
    config.input.path.rename(renamed)
    assert discover_csv_files(renamed.parent) == [renamed]


def test_unknown_dates_are_not_mistaken_for_duplicate_keys(config):
    raw = (
        pl.read_csv(config.input.path)
        .with_row_index("i")
        .with_columns(
            pl.when(pl.col("i") < 2)
            .then(pl.lit("bad-date"))
            .otherwise(pl.col("trade_date"))
            .alias("trade_date")
        )
        .drop("i")
    )
    raw.write_csv(config.input.path)
    config.validation.duplicate_policy = "reject"
    result = ingest(config)
    assert result.report["errors_by_category"] == {"malformed_value": 2}


def test_inputs_changed_during_materialization_fail_before_publication(config, monkeypatch):
    from research_data_engine import pipeline

    original_scan = pipeline.scan_prices

    class ChangingScan:
        def __init__(self, lazy):
            self.lazy = lazy

        def collect(self, **kwargs):
            collected = self.lazy.collect(**kwargs)
            with config.input.path.open("a") as handle:
                handle.write("\n")
            return collected

    def scan_with_change(settings):
        lazy, files = original_scan(settings)
        return ChangingScan(lazy), files

    monkeypatch.setattr(pipeline, "scan_prices", scan_with_change)
    with pytest.raises(IngestionError, match="Input changed during ingestion"):
        ingest(config)
    assert not (config.output.path / "CURRENT.json").exists()
