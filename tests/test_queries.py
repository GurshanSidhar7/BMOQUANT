import math

import polars as pl
import pytest

from research_data_engine import QueryEngine, ingest, load_prices
from research_data_engine.exceptions import QueryError


def test_filtering_grouped_aggregations_and_history(config):
    ingest(config)
    with QueryEngine(config.output.path) as engine:
        all_prices = engine.load_prices()
        symbol = all_prices["symbol"][0]
        start, end = all_prices["date"][10], all_prices["date"][20]
        filtered = engine.load_prices(symbols=[symbol.lower()], start=str(start), end=str(end))
        assert filtered.height == 11
        assert filtered["simple_return"][0] == all_prices["simple_return"][10]
        actual = engine.query("""
            SELECT symbol, source, avg(volume) AS volume, avg(simple_return) AS simple_return
            FROM prices GROUP BY symbol, source ORDER BY symbol, source
        """)
        expected = (
            all_prices.group_by("symbol", "source")
            .agg(pl.col("volume").mean(), pl.col("simple_return").mean())
            .sort("symbol", "source")
        )
        assert actual["volume"].to_list() == pytest.approx(expected["volume"].to_list())
        assert actual["simple_return"].to_list() == pytest.approx(
            expected["simple_return"].to_list()
        )
        assert engine.load_prices(symbols=[]).is_empty()


def test_sql_window_volatility_agrees_with_polars(config):
    ingest(config)
    with QueryEngine(config.output.path) as engine:
        actual = engine.query("""
            SELECT symbol, source, date, realized_vol_20,
                CASE WHEN count(log_return) OVER w = 20
                THEN stddev_samp(log_return) OVER w * sqrt(252) END AS sql_vol
            FROM prices WINDOW w AS (
                PARTITION BY symbol, source ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            ) ORDER BY symbol, source, date
        """)
        for row in actual.select("realized_vol_20", "sql_vol").iter_rows():
            if row[0] is None:
                assert row[1] is None
            else:
                assert math.isclose(row[0], row[1], rel_tol=1e-10)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM prices",
        "SELECT 1; SELECT 2",
        "CREATE TABLE x AS SELECT 1",
        "COPY (SELECT 1) TO 'output.csv'",
        "SET enable_external_access=true",
        "PRAGMA version",
        "ATTACH 'other.duckdb' AS other",
        "",
    ],
)
def test_rejects_non_select_or_multiple_statements(config, sql):
    ingest(config)
    with (
        QueryEngine(config.output.path) as engine,
        pytest.raises(QueryError, match="single read-only SELECT"),
    ):
        engine.query(sql)


def test_unapproved_file_access_is_blocked(config, tmp_path):
    ingest(config)
    secret = tmp_path / "unapproved.txt"
    secret.write_text("local file not in allowed paths")
    with QueryEngine(config.output.path) as engine:
        with pytest.raises(QueryError, match="disabled|Permission"):
            engine.query("SELECT * FROM read_text(?)", [str(secret)])
        assert (
            engine.query("WITH x AS (SELECT count(*) n FROM prices) SELECT n FROM x")["n"][0] == 100
        )


def test_symbols_are_parameterized_and_dates_checked(config):
    ingest(config)
    assert load_prices(dataset=config.output.path, symbols=["' OR TRUE --"]).is_empty()
    with pytest.raises(QueryError, match="ISO date"):
        load_prices(dataset=config.output.path, start="bad")
    with pytest.raises(QueryError, match="start must"):
        load_prices(dataset=config.output.path, start="2025-02-01", end="2025-01-01")
