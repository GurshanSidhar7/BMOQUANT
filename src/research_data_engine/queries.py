"""Local DuckDB analytical SQL over one resolved, immutable Parquet snapshot."""

import re
from datetime import date
from pathlib import Path
from typing import Any, Self

import duckdb
import polars as pl

from research_data_engine.exceptions import QueryError
from research_data_engine.storage import read_snapshot

DEFAULT_DATASET = Path("data/processed/equity_prices")


class QueryEngine:
    """Expose the active snapshot as `prices`; user SQL must be one SELECT.

    Disable extension installation, Python replacement scans, and external access
    except the resolved Parquet file. These are local safeguards, not a sandbox
    for hostile SQL. Queries can still consume substantial CPU and memory.
    """

    def __init__(self, dataset: str | Path = DEFAULT_DATASET) -> None:
        self.snapshot = read_snapshot(dataset)
        self.connection = duckdb.connect(
            config={
                "autoinstall_known_extensions": False,
                "autoload_known_extensions": False,
                "python_enable_replacements": False,
            }
        )
        try:
            self.connection.execute("SET allowed_paths = ?", [[str(self.snapshot.prices_path)]])
            self.connection.execute("SET enable_external_access = false")
            self.connection.from_parquet(str(self.snapshot.prices_path)).create_view("prices")
            self.connection.execute("SET lock_configuration = true")
        except duckdb.Error as exc:
            self.connection.close()
            raise QueryError(f"Cannot open analytical snapshot: {exc}") from exc

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def query(self, sql: str, parameters: list[Any] | None = None) -> pl.DataFrame:
        """Parse with DuckDB itself, rejecting multiple statements and all non-SELECTs."""
        try:
            statements = self.connection.extract_statements(sql)
            tokens = duckdb.tokenize(sql)
            starts_select = bool(tokens) and re.match(
                r"(?:SELECT|WITH)\b", sql[tokens[0][0] :], re.IGNORECASE
            )
            if (
                not starts_select
                or len(statements) != 1
                or statements[0].type != duckdb.StatementType.SELECT
            ):
                raise QueryError("Only a single read-only SELECT (including WITH) is supported")
            return self.connection.execute(sql, parameters or []).pl()
        except duckdb.Error as exc:
            raise QueryError(f"Analytical SQL failed: {exc}") from exc

    def load_prices(
        self,
        *,
        symbols: list[str] | None = None,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> pl.DataFrame:
        """Filter after stored analytics: returns retain pre-start historical context."""
        conditions = []
        parameters: list[Any] = []
        if symbols is not None:
            if not symbols:
                return self.query("SELECT * FROM prices WHERE FALSE")
            conditions.append("symbol IN (" + ",".join("?" for _ in symbols) + ")")
            parameters.extend(s.strip().upper() for s in symbols)
        for value, operator in ((start, ">="), (end, "<=")):
            if value is not None:
                try:
                    parsed = date.fromisoformat(value) if isinstance(value, str) else value
                except ValueError as exc:
                    raise QueryError(f"Invalid ISO date: {value}") from exc
                conditions.append(f"date {operator} ?")
                parameters.append(parsed)
        if start is not None and end is not None and str(start) > str(end):
            raise QueryError("start must be on or before end")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return self.query(
            "SELECT * FROM prices" + where + " ORDER BY symbol, source, date", parameters
        )


def load_prices(
    *,
    dataset: str | Path = DEFAULT_DATASET,
    symbols: list[str] | None = None,
    start: str | date | None = None,
    end: str | date | None = None,
) -> pl.DataFrame:
    """Load a research slice as Polars, keeping independent source observations."""
    with QueryEngine(dataset) as engine:
        return engine.load_prices(symbols=symbols, start=start, end=end)
