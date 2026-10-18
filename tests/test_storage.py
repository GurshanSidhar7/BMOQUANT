import json

import polars as pl
import pytest

from research_data_engine import ingest, load_prices, read_snapshot
from research_data_engine.exceptions import DataValidationError, StorageError
from research_data_engine.storage import publish_snapshot
from research_data_engine.transformations import PRICE_SCHEMA


def test_parquet_round_trip_and_idempotent_ingestion(config):
    first = ingest(config)
    before = load_prices(dataset=config.output.path)
    second = ingest(config)
    after = load_prices(dataset=config.output.path)
    assert before.equals(after)
    assert before.height == 100
    assert first.snapshot.version != second.snapshot.version
    assert {c: after.schema[c] for c in PRICE_SCHEMA} == PRICE_SCHEMA
    metadata = json.loads((second.snapshot.directory / "metadata.json").read_text())
    assert metadata["input_files"][0]["sha256"] == first.report["input_files"][0]["sha256"]


def test_publication_failure_preserves_previous_snapshot(config, monkeypatch):
    first = ingest(config)
    before = load_prices(dataset=config.output.path)

    def fail_pointer(*_):
        raise OSError("injected publication failure")

    monkeypatch.setattr("research_data_engine.storage._publish_pointer", fail_pointer)
    with pytest.raises(StorageError, match="injected publication failure"):
        ingest(config)
    assert read_snapshot(config.output.path).version == first.snapshot.version
    assert load_prices(dataset=config.output.path).equals(before)
    assert not list(config.output.path.glob(".staging-*"))
    assert len(list((config.output.path / "versions").iterdir())) == 1


def test_rejected_run_preserves_previous_snapshot(config):
    first = ingest(config)
    raw = pl.read_csv(config.input.path).with_columns(pl.lit(-1).alias("volume"))
    raw.write_csv(config.input.path)
    config.validation.invalid_price_policy = "reject"
    with pytest.raises(DataValidationError, match="Previous snapshot remains active"):
        ingest(config)
    assert read_snapshot(config.output.path).version == first.snapshot.version


def test_refuses_unmanaged_directory(tmp_path, prices):
    (tmp_path / "valuable.txt").write_text("keep me")
    with pytest.raises(StorageError, match="unmanaged"):
        publish_snapshot(tmp_path, prices, prices.head(0), {})
    assert (tmp_path / "valuable.txt").read_text() == "keep me"


def test_manifest_cannot_escape_version_directory(tmp_path):
    (tmp_path / "CURRENT.json").write_text(
        '{"format":"research-data-engine-v1","version":"../../other"}'
    )
    with pytest.raises(StorageError, match="Invalid snapshot manifest"):
        read_snapshot(tmp_path)
