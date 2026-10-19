import json

from typer.testing import CliRunner

from research_data_engine.cli import app
from research_data_engine.sample_data import write_sample_csv

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("ingest", "validate", "query", "demo", "benchmark"):
        assert command in result.stdout


def test_invalid_config_exits_nonzero(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("unknown_field: true")
    result = runner.invoke(app, ["ingest", "--config", str(path)])
    assert result.exit_code == 1
    assert "Cannot load configuration" in result.stdout


def test_full_demo_validate_and_query(tmp_path):
    result = runner.invoke(app, ["demo", "--directory", str(tmp_path)])
    assert result.exit_code == 0, result.stdout + str(result.exception)
    assert "SYNTHETIC" in result.stdout
    dataset = tmp_path / "processed" / "equity_prices"
    validation = runner.invoke(app, ["validate", "--dataset", str(dataset)])
    assert validation.exit_code == 0, validation.stdout + str(validation.exception)
    sql = tmp_path / "analysis.sql"
    sql.write_text("SELECT count(*) AS rows FROM prices")
    query = runner.invoke(app, ["query", "--dataset", str(dataset), "--sql", str(sql)])
    assert query.exit_code == 0, query.stdout
    manifest = json.loads((dataset / "CURRENT.json").read_text())
    report = json.loads((dataset / "versions" / manifest["version"] / "report.json").read_text())
    assert report["input_row_count"] == 13_041
    assert report["quarantined_row_count"] == 7
    assert report["valid_row_count"] == 13_034


def test_generator_is_deterministic(tmp_path):
    first = write_sample_csv(tmp_path / "one.csv", symbols=2, rows=50)
    second = write_sample_csv(tmp_path / "two.csv", symbols=2, rows=50)
    assert first.read_bytes() == second.read_bytes()
