import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_walkthrough.py"
SPEC = importlib.util.spec_from_file_location("walkthrough_export", SCRIPT)
assert SPEC and SPEC.loader
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("walkthrough-evidence")
    result = exporter.export_walkthrough(directory)
    return directory, result


def test_export_preserves_actual_decisions_and_portable_strict_json(bundle):
    directory, result = bundle
    report = result["report"]
    assert report["input_row_count"] == 65_201
    assert report["valid_row_count"] + report["quarantined_row_count"] == 65_201
    bad = [row for row in result["records"] if row["status"] == "quarantined"]
    assert len(bad) == report["quarantined_row_count"] == 7
    assert sum("duplicate_key" in row["errors"] for row in bad) == 2
    assert next(row for row in bad if row["row"] == 6)["canonical"]["close"] == "NaN"
    serialized = (directory / "evidence.json").read_text()
    assert "/Users/" not in serialized
    assert "/private/" not in serialized
    assert "/tmp/rde-walkthrough" not in serialized
    assert json.loads(serialized)["policy_preview"]["reject"]["published_rows"] == 0


def test_exported_financial_history_matches_recorded_duckdb_results(bundle):
    _, result = bundle
    query = next(query for query in result["queries"] if query["id"] == "daily_returns")
    observed = query["rows"][0]
    stored = next(
        row for row in result["series"][observed["symbol"]] if row["date"] == observed["date"]
    )
    assert observed["simple_return"] == pytest.approx(stored["simple_return"])
    assert stored["realized_vol_20"] is not None
    assert result["report"]["config"]["schema"]["source"] == "source"
    directory, _ = bundle
    checksums = json.loads((directory / "checksums.json").read_text())
    for name, checksum in checksums.items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == checksum


def test_failed_test_evidence_cannot_be_published(tmp_path):
    junit = tmp_path / "failed.xml"
    junit.write_text('<testsuites><testsuite tests="2" failures="1" errors="0"/></testsuites>')
    with pytest.raises(ValueError, match="failing or empty"):
        exporter.export_walkthrough(tmp_path / "assets", junit)
    assert not (tmp_path / "assets").exists()
