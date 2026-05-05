"""compare_periods tool — headline before/after diff for a named metric.

Use this FIRST when the question is "did X move, and how much?"
Returns one row: {before_value, after_value, abs_delta, pct_delta}.
Does NOT tell you which slice drove the change — call decompose_metric for that.
Never raises — all failures come back as {error, hint}.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb
import yaml

from agent.constants import (
    DEFAULT_PARQUET_DIR,
    DEFAULT_SEMANTIC_LAYER_PATH,
    ENV_SEMANTIC_LAYER_PATH,
)
from agent.tools.run_sql import build_connection
from agent.tools.schemas import ComparePeriodsInput, ComparePeriodsOutput, TimeWindow

logger = logging.getLogger(__name__)


def _fact_table_from_metric(metric: dict) -> str:
    """Derive the fact table name from the metric's time_column (e.g. 'events.ts' → 'events')."""
    tc = metric.get("time_column") or ""
    if tc and "." in tc:
        return tc.split(".")[0]
    return "fact"


def _build_join_overrides(joins_raw: list) -> dict[str, str]:
    """Build a {right_table: JOIN_clause} dict from the semantic layer joins section."""
    overrides: dict[str, str] = {}
    for j in joins_raw:
        if not isinstance(j, dict):
            continue
        left = j.get("left", "")
        right = j.get("right", "")
        join_kind = j.get("join_kind", "left").upper()
        if not left or not right or "." not in right:
            continue
        right_table = right.split(".")[0]
        overrides[right_table] = f"{join_kind} JOIN {right_table} ON {left} = {right}"
    return overrides


def _resolve_metric_sql(metric_name: str, metric: dict) -> tuple[str, str | None]:
    """Build a complete SELECT … AS value FROM <fact_table> SQL from a metric definition.

    Handles bare aggregate expressions, full SELECT statements, and ratio metrics
    (type: ratio with numerator/denominator fields). Returns (sql, error).
    """
    fact = _fact_table_from_metric(metric)
    if "sql" in metric:
        sql = metric["sql"].strip()
        if sql.upper().startswith("SELECT"):
            return sql, None
        return f"SELECT {sql} AS value FROM {fact}", None

    if metric.get("type") == "ratio":
        num = metric.get("numerator")
        den = metric.get("denominator")
        if num and den:
            return (
                f"SELECT CAST(({num}) AS DOUBLE) / NULLIF(({den}), 0.0) AS value FROM {fact}",
                None,
            )
        return "", f"Metric {metric_name!r} has type=ratio but is missing numerator/denominator."

    return "", f"Metric {metric_name!r} has no 'sql' field and is not a recognized ratio type."


def _load_yaml(path: Path) -> tuple[dict, str | None]:
    try:
        return yaml.safe_load(path.read_text()), None
    except FileNotFoundError:
        return {}, f"Semantic layer file not found: {path}"
    except yaml.YAMLError as exc:
        return {}, f"Failed to parse semantic layer YAML: {exc}"
    except Exception as exc:
        return {}, f"Unexpected error reading semantic layer: {exc}"


def _resolve_dim_sql(dim_name: str, dim: dict) -> tuple[str, str | None]:
    """Return the SQL expression for a dimension from any of the three YAML formats.

    Dimensions in the semantic layer use one of: `sql:`, `sql_case:`, or `table: + column:`.
    Returns (sql_expression, error_message).
    """
    if "sql" in dim:
        return dim["sql"], None
    if "sql_case" in dim:
        return dim["sql_case"], None
    col = dim.get("column")
    if col:
        tbl = dim.get("table")
        return f"{tbl}.{col}" if tbl else col, None
    return "", (
        f"Dimension {dim_name!r} has no 'sql', 'sql_case', or 'column' field in the semantic layer."
    )


def _inject_joins(
    sql: str,
    dimensions_raw: dict,
    join_overrides: dict[str, str],
    dim_name: str | None = None,
) -> str:
    """Append missing JOINs for tables referenced in dimension SQL but absent from the FROM clause.

    Only tables not already mentioned in the SQL get JOINs appended. This keeps the SQL portable
    across any parquet set while enabling cross-table GROUP BYs.
    """
    needed: set[str] = set()
    for name, dim in dimensions_raw.items():
        if dim_name is not None and name != dim_name:
            continue
        dim_sql, _ = _resolve_dim_sql(name, dim)
        upper_sql = sql.upper()
        for tbl in join_overrides:
            if tbl.upper() in dim_sql.upper():
                col_ref = f"{tbl.upper()}."
                join_ref = f"JOIN {tbl.upper()}"
                if col_ref in upper_sql and join_ref not in upper_sql:
                    needed.add(tbl)

    if not needed:
        return sql

    stripped = sql.rstrip()
    has_where = "WHERE" in stripped.upper()
    join_block = "\n".join(join_overrides[t] for t in sorted(needed))
    if has_where:
        idx = stripped.upper().rindex("WHERE")
        return stripped[:idx] + join_block + "\n" + stripped[idx:]
    return stripped + "\n" + join_block


def _inject_segment(sql: str, segment: dict, dimensions_raw: dict) -> tuple[str, list, str | None]:
    """Append segment WHERE conditions to the metric SQL using parameterized values.

    Returns (modified_sql, params, error_message). error_message is None on success.
    Dimension SQL expressions come from the trusted YAML; only values are parameterized.

    WHERE detection uses a simple string check, which is reliable for the metric SQLs
    in this project (they are short, flat SELECTs — no CTEs or nested subqueries).
    """
    if not segment:
        return sql, [], None

    conditions: list[str] = []
    params: list = []
    for dim_name, dim_value in segment.items():
        if dim_name not in dimensions_raw:
            available = list(dimensions_raw.keys())
            return (
                sql,
                [],
                (
                    f"Dimension {dim_name!r} not found in semantic layer. "
                    f"Available dimensions: {available}."
                ),
            )
        dim_sql, dim_err = _resolve_dim_sql(dim_name, dimensions_raw[dim_name])
        if dim_err:
            return sql, [], dim_err
        conditions.append(f"({dim_sql}) = ?")
        params.append(dim_value)

    clause = " AND ".join(conditions)
    stripped = sql.rstrip()
    if "WHERE" in stripped.upper():
        return stripped + f"\nAND {clause}", params, None
    return stripped + f"\nWHERE {clause}", params, None


def _run_metric(
    metric_sql: str,
    time_column: str | None,
    window: TimeWindow,
    segment: dict | None,
    dimensions_raw: dict,
    join_overrides: dict[str, str],
    conn: duckdb.DuckDBPyConnection,
) -> tuple[float | None, str | None]:
    """Execute the metric SQL for one time window.

    Returns (value, error_message). value is None for NULL results.
    """
    sql = metric_sql.strip()
    params: list = []

    # Inject time filter. Prefer explicit :start/:end placeholders in the metric SQL;
    # fall back to appending a WHERE clause using time_column directly.
    if time_column:
        if ":start" in sql or ":end" in sql:
            sql = sql.replace(":start", f"'{window.start}'").replace(":end", f"'{window.end}'")
        else:
            clause = f"{time_column} >= '{window.start}' AND {time_column} < '{window.end}'"
            if "WHERE" in sql.upper():
                sql = sql + f"\nAND {clause}"
            else:
                sql = sql + f"\nWHERE {clause}"

    # Inject segment conditions using parameterized values.
    if segment:
        sql, params, err = _inject_segment(sql, segment, dimensions_raw)
        if err:
            return None, err

    # Append missing JOINs for tables referenced in dimension SQL.
    sql = _inject_joins(sql, dimensions_raw, join_overrides)

    try:
        row = conn.execute(sql, params).fetchone()
        value = float(row[0]) if row and row[0] is not None else None
        return value, None
    except Exception as exc:
        return None, str(exc)


def compare_periods(
    args: ComparePeriodsInput,
    conn: duckdb.DuckDBPyConnection | None = None,
    semantic_layer_path: str | None = None,
) -> ComparePeriodsOutput:
    """Compute headline before/after diff for a named metric.

    Call this first when asked "did X move?" Pass the baseline period as `before`
    and the comparison period as `after`. Use decompose_metric afterwards to find
    which slice drove the movement.
    All errors are returned as {error, hint} — never raised.
    """
    path = Path(
        semantic_layer_path or os.getenv(ENV_SEMANTIC_LAYER_PATH, DEFAULT_SEMANTIC_LAYER_PATH)
    )
    raw, err = _load_yaml(path)
    if err:
        return ComparePeriodsOutput(
            before_value=None,
            after_value=None,
            abs_delta=None,
            pct_delta=None,
            error=err,
            hint="Check SEMANTIC_LAYER_PATH env var or ensure data/semantic_layer.yml exists.",
        )

    metrics_raw: dict = raw.get("metrics") or {}
    dimensions_raw: dict = raw.get("dimensions") or {}
    join_overrides = _build_join_overrides(raw.get("joins") or [])

    if args.metric not in metrics_raw:
        available = list(metrics_raw.keys())
        return ComparePeriodsOutput(
            before_value=None,
            after_value=None,
            abs_delta=None,
            pct_delta=None,
            error=f"Metric {args.metric!r} not found in semantic layer.",
            hint=f"Available metrics: {available}. Call inspect_schema with no args to see all.",
        )

    metric = metrics_raw[args.metric]
    metric_sql, build_err = _resolve_metric_sql(args.metric, metric)
    if build_err:
        return ComparePeriodsOutput(
            before_value=None,
            after_value=None,
            abs_delta=None,
            pct_delta=None,
            error=build_err,
            hint="Fix the semantic layer YAML or call inspect_schema to check metric definitions.",
        )
    time_column: str | None = metric.get("time_column")
    if not time_column:
        return ComparePeriodsOutput(
            before_value=None,
            after_value=None,
            abs_delta=None,
            pct_delta=None,
            error=f"Metric {args.metric!r} has no time_column — before/after windows cannot be applied.",
            hint=(
                "Use run_sql with an explicit WHERE clause to compare time periods, "
                "or add time_column to this metric in the semantic layer."
            ),
        )

    # _conn is assigned inside the try so the finally block always has it in scope.
    _conn: duckdb.DuckDBPyConnection | None = None
    try:
        _conn = (
            conn
            if conn is not None
            else build_connection(os.getenv("PARQUET_DIR", DEFAULT_PARQUET_DIR))
        )
        before_value, err = _run_metric(
            metric_sql,
            time_column,
            args.before,
            args.segment,
            dimensions_raw,
            join_overrides,
            _conn,
        )
        if err:
            return ComparePeriodsOutput(
                before_value=None,
                after_value=None,
                abs_delta=None,
                pct_delta=None,
                error=f"Error computing before window: {err}",
                hint="Check the metric SQL and segment dimension names with inspect_schema.",
            )

        after_value, err = _run_metric(
            metric_sql, time_column, args.after, args.segment, dimensions_raw, join_overrides, _conn
        )
        if err:
            return ComparePeriodsOutput(
                before_value=None,
                after_value=None,
                abs_delta=None,
                pct_delta=None,
                error=f"Error computing after window: {err}",
                hint="Check the metric SQL and segment dimension names with inspect_schema.",
            )
    finally:
        if conn is None and _conn is not None:
            _conn.close()

    abs_delta: float | None = None
    pct_delta: float | None = None
    if before_value is not None and after_value is not None:
        abs_delta = after_value - before_value
        pct_delta = (abs_delta / before_value * 100.0) if before_value != 0.0 else None

    return ComparePeriodsOutput(
        before_value=before_value,
        after_value=after_value,
        abs_delta=abs_delta,
        pct_delta=pct_delta,
    )
