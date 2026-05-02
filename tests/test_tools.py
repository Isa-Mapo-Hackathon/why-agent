"""Smoke tests for agent/tools/schemas.py, run_sql.py, and inspect_schema.py.

Tests verify shape and error-handling behaviour. Real in-memory DuckDB is used
for run_sql; inspect_schema tests use a minimal in-memory YAML fixture.
"""

import duckdb
import pytest

from agent.tools.inspect_schema import inspect_schema
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
# Shared YAML fixture for inspect_schema tests
# ---------------------------------------------------------------------------

_MINIMAL_YAML = """\
tables:
  items:
    file: items.parquet
    grain: "One row per item."
    description: "Grocery catalog."
    columns:
      - name: id
        type: BIGINT
        description: "Primary key."
      - name: price
        type: DOUBLE
        description: "Price in USD."
    joins:
      - "items.id = item_nutrition.item_id"
  orders:
    file: orders.parquet
    grain: "One row per order."
    description: "Order records."
    columns:
      - name: id
        type: BIGINT
        description: "Order ID."

metrics:
  avg_price:
    description: "Mean price."
    sql: "SELECT AVG(price) FROM items"
    time_column: null
  order_count:
    description: "Number of orders."
    sql: "SELECT COUNT(*) FROM orders"
    time_column: orders.created_at

dimensions:
  store:
    description: "Store name."
    sql: "items.store"
    cardinality: 2
"""


@pytest.fixture
def sl_path(tmp_path: pytest.TempPathFactory) -> str:
    """Write the minimal YAML to a temp file; return its path as a string."""
    p = tmp_path / "semantic_layer.yml"
    p.write_text(_MINIMAL_YAML)
    return str(p)


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


# ---------------------------------------------------------------------------
# inspect_schema behaviour
# ---------------------------------------------------------------------------


class TestInspectSchema:
    def test_list_all_returns_tables_metrics_dimensions(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(), sl_path)

        assert result.error is None
        assert result.tables is not None
        assert result.metrics is not None
        assert result.dimensions is not None
        assert result.table is None

    def test_list_all_table_names(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(), sl_path)

        assert set(result.tables) == {"items", "orders"}

    def test_list_all_metric_names(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(), sl_path)

        assert set(result.metrics) == {"avg_price", "order_count"}

    def test_list_all_dimension_names(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(), sl_path)

        assert result.dimensions == ["store"]

    def test_describe_table_returns_summary(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(table="items"), sl_path)

        assert result.error is None
        assert result.table is not None
        assert result.table.name == "items"
        assert result.table.description == "Grocery catalog."
        assert result.table.grain == "One row per item."
        assert result.tables is None
        assert result.metrics is None

    def test_describe_table_columns_shape(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(table="items"), sl_path)

        cols = result.table.columns
        assert len(cols) == 2
        assert cols[0].name == "id"
        assert cols[0].type == "BIGINT"
        assert cols[1].name == "price"

    def test_describe_table_joins(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(table="items"), sl_path)

        assert result.table.joins == ["items.id = item_nutrition.item_id"]

    def test_table_with_no_joins(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(table="orders"), sl_path)

        assert result.table.joins == []

    def test_unknown_table_returns_error(self, sl_path: str) -> None:
        result = inspect_schema(InspectSchemaInput(table="nonexistent"), sl_path)

        assert result.error is not None
        assert result.hint is not None
        assert "nonexistent" in result.error

    def test_missing_yaml_returns_error(self, tmp_path: pytest.TempPathFactory) -> None:
        result = inspect_schema(InspectSchemaInput(), str(tmp_path / "missing.yml"))

        assert result.error is not None
        assert result.hint is not None

    def test_null_yaml_values_do_not_raise(self, tmp_path: pytest.TempPathFactory) -> None:
        # `tables: null` in YAML — must not crash with AttributeError on .keys()
        p = tmp_path / "null.yml"
        p.write_text("tables:\nmetrics:\ndimensions:\n")
        result = inspect_schema(InspectSchemaInput(), str(p))

        assert result.error is None
        assert result.tables == []
        assert result.metrics == []
        assert result.dimensions == []

    def test_malformed_column_returns_error(self, tmp_path: pytest.TempPathFactory) -> None:
        # Column entry missing 'type' — must return {error, hint}, not raise
        p = tmp_path / "bad.yml"
        p.write_text(
            "tables:\n  t:\n    grain: g\n    description: d\n    columns:\n      - name: x\n"
        )
        result = inspect_schema(InspectSchemaInput(table="t"), str(p))

        assert result.error is not None
        assert result.hint is not None

    def test_env_var_default_path(self, sl_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEMANTIC_LAYER_PATH", sl_path)
        result = inspect_schema(InspectSchemaInput())  # no path arg — uses env var

        assert result.error is None
        assert "items" in result.tables
