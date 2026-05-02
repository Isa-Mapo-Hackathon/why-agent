"""Smoke tests for agent/tools/schemas.py and agent/tools/run_sql.py.

Tests verify shape and error-handling behaviour. Real in-memory DuckDB is used
— no mocking of the DB layer.
"""

import duckdb
import pytest

from agent.tools.run_sql import build_connection, run_sql
from agent.tools.schemas import (
    ComparePeriodsInput,
    DecomposeMetricInput,
    InspectSchemaInput,
    RunSqlInput,
    RunSqlOutput,
    TimeWindow,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with a small products table."""
    c = duckdb.connect()
    c.execute("""
        CREATE TABLE products AS
        SELECT * FROM (VALUES
            (1, 'Apple',  1.50, 'Fruit'),
            (2, 'Banana', 0.75, 'Fruit'),
            (3, 'Milk',   3.20, 'Dairy'),
            (4, 'Cheese', 8.99, 'Dairy'),
            (5, 'Bread',  2.50, 'Bakery')
        ) t(id, name, price, category)
    """)
    return c


# ---------------------------------------------------------------------------
# RunSqlInput schema
# ---------------------------------------------------------------------------


class TestRunSqlInput:
    def test_valid_input(self) -> None:
        inp = RunSqlInput(query="SELECT 1", max_rows=50)
        assert inp.query == "SELECT 1"
        assert inp.max_rows == 50

    def test_default_max_rows(self) -> None:
        inp = RunSqlInput(query="SELECT 1")
        assert inp.max_rows == 100

    def test_max_rows_lower_bound_rejected(self) -> None:
        with pytest.raises(Exception):
            RunSqlInput(query="SELECT 1", max_rows=0)

    def test_max_rows_upper_bound_rejected(self) -> None:
        with pytest.raises(Exception):
            RunSqlInput(query="SELECT 1", max_rows=1001)


# ---------------------------------------------------------------------------
# RunSqlOutput schema
# ---------------------------------------------------------------------------


class TestRunSqlOutput:
    def test_success_output_has_no_error(self) -> None:
        out = RunSqlOutput(rows=[{"id": 1}], truncated=False, row_count=1, execution_ms=5.2)
        assert out.error is None
        assert out.hint is None

    def test_error_output_carries_hint(self) -> None:
        out = RunSqlOutput(
            rows=[],
            truncated=False,
            row_count=0,
            execution_ms=0.0,
            error="bad query",
            hint="check column names",
        )
        assert out.error == "bad query"
        assert out.hint == "check column names"


# ---------------------------------------------------------------------------
# TimeWindow schema
# ---------------------------------------------------------------------------


class TestTimeWindow:
    def test_valid_window(self) -> None:
        w = TimeWindow(start="2026-01-01", end="2026-02-01")
        assert w.start == "2026-01-01"
        assert w.end == "2026-02-01"

    def test_rejects_non_iso_string(self) -> None:
        with pytest.raises(Exception, match="ISO date"):
            TimeWindow(start="tomorrow", end="2026-02-01")

    def test_rejects_invalid_date(self) -> None:
        with pytest.raises(Exception):
            TimeWindow(start="2026-13-01", end="2026-02-01")


# ---------------------------------------------------------------------------
# InspectSchemaInput schema
# ---------------------------------------------------------------------------


class TestInspectSchemaInput:
    def test_defaults_to_no_table(self) -> None:
        assert InspectSchemaInput().table is None

    def test_accepts_table_name(self) -> None:
        assert InspectSchemaInput(table="items").table == "items"


# ---------------------------------------------------------------------------
# ComparePeriodsInput schema
# ---------------------------------------------------------------------------


class TestComparePeriodsInput:
    def test_valid_without_segment(self) -> None:
        inp = ComparePeriodsInput(
            metric="avg_price",
            before=TimeWindow(start="2026-01-01", end="2026-02-01"),
            after=TimeWindow(start="2026-02-01", end="2026-03-01"),
        )
        assert inp.segment is None

    def test_valid_with_segment(self) -> None:
        inp = ComparePeriodsInput(
            metric="avg_price",
            before=TimeWindow(start="2026-01-01", end="2026-02-01"),
            after=TimeWindow(start="2026-02-01", end="2026-03-01"),
            segment={"store": "WHOLE_FOODS"},
        )
        assert inp.segment == {"store": "WHOLE_FOODS"}


# ---------------------------------------------------------------------------
# DecomposeMetricInput schema
# ---------------------------------------------------------------------------


class TestDecomposeMetricInput:
    def test_valid_input(self) -> None:
        inp = DecomposeMetricInput(
            metric="avg_price",
            dimensions=["store", "category"],
            time_window=TimeWindow(start="2026-01-01", end="2026-04-01"),
        )
        assert len(inp.dimensions) == 2


# ---------------------------------------------------------------------------
# run_sql behaviour
# ---------------------------------------------------------------------------


class TestRunSql:
    def test_returns_expected_shape(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(RunSqlInput(query="SELECT id, name FROM products"), conn)

        assert isinstance(result, RunSqlOutput)
        assert result.error is None
        assert result.row_count == 5
        assert result.truncated is False
        assert result.execution_ms >= 0
        assert "id" in result.rows[0]
        assert "name" in result.rows[0]

    def test_truncation_at_max_rows(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(RunSqlInput(query="SELECT * FROM products", max_rows=3), conn)

        assert result.truncated is True
        assert result.row_count == 3
        assert len(result.rows) == 3

    def test_no_truncation_when_rows_fit(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(RunSqlInput(query="SELECT * FROM products", max_rows=100), conn)

        assert result.truncated is False

    def test_rejects_drop(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(RunSqlInput(query="DROP TABLE products"), conn)

        assert result.error is not None
        assert result.hint is not None
        assert result.row_count == 0

    def test_rejects_insert(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(RunSqlInput(query="INSERT INTO products VALUES (6, 'X', 1.0, 'Y')"), conn)

        assert result.error is not None

    def test_with_cte(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(
            RunSqlInput(
                query="WITH cheap AS (SELECT * FROM products WHERE price < 2) SELECT * FROM cheap"
            ),
            conn,
        )

        assert result.error is None
        assert result.row_count == 2  # Apple (1.50) and Banana (0.75)

    def test_bad_table_returns_error_dict(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(RunSqlInput(query="SELECT * FROM nonexistent"), conn)

        assert result.error is not None
        assert result.hint is not None
        assert result.rows == []

    def test_execution_ms_non_negative(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(RunSqlInput(query="SELECT 1"), conn)

        assert result.execution_ms >= 0

    def test_rows_are_dicts_with_correct_values(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(RunSqlInput(query="SELECT id, price FROM products WHERE id = 1"), conn)

        assert len(result.rows) == 1
        assert result.rows[0]["id"] == 1
        assert result.rows[0]["price"] == pytest.approx(1.50)

    def test_rejects_semicolon_injection(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = run_sql(
            RunSqlInput(query="WITH x AS (SELECT 1) SELECT * FROM x; DROP TABLE products"),
            conn,
        )

        assert result.error is not None

    def test_no_conn_uses_parquet_dir(self, tmp_path: pytest.TempPathFactory) -> None:
        # Write a tiny parquet file, point build_connection at it, run a query.
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({"id": [1, 2], "val": ["a", "b"]})
        pq.write_table(table, tmp_path / "things.parquet")

        conn = build_connection(str(tmp_path))
        result = run_sql(RunSqlInput(query="SELECT COUNT(*) AS n FROM things"), conn)

        assert result.error is None
        assert result.rows[0]["n"] == 2
