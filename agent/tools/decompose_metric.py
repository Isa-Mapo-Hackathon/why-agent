"""decompose_metric tool — drill down to find WHICH slice drove a metric movement.

Use this AFTER compare_periods has confirmed a delta and you need to attribute it.
For each dimension, slices the metric over a time window and ranks slices by
anomaly magnitude (deviation from the mean across all slices).
Never raises — all failures come back as {error, hint}.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import duckdb
import yaml

from agent.constants import (
    DEFAULT_PARQUET_DIR,
    DEFAULT_SEMANTIC_LAYER_PATH,
    ENV_SEMANTIC_LAYER_PATH,
)
from agent.tools.run_sql import build_connection
from agent.tools.schemas import (
    DecomposeMetricInput,
    DecomposeMetricOutput,
    SliceResult,
    TimeWindow,
)

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


def _inject_joins(sql: str, dim_sql: str, join_overrides: dict[str, str]) -> str:
    """Append missing JOINs for tables referenced in dim_sql but absent from the FROM clause.

    Only tables not already joined (no JOIN keyword for that table in the SQL) get JOINs appended.
    """
    needed = []
    for tbl in join_overrides:
        if tbl.upper() in dim_sql.upper():
            upper = sql.upper()
            if f"{tbl.upper()}." in upper and f"JOIN {tbl.upper()}" not in upper:
                needed.append(tbl)
    if not needed:
        return sql
    stripped = sql.rstrip()
    has_where = "WHERE" in stripped.upper()
    join_block = "\n".join(join_overrides[t] for t in sorted(needed))
    if has_where:
        idx = stripped.upper().rindex("WHERE")
        return stripped[:idx] + join_block + "\n" + stripped[idx:]
    return stripped + "\n" + join_block


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


# Matches: SELECT <agg_expr> AS value <rest>
# Works for the flat metric SQLs in this project (no nested SELECTs before AS value).
_SELECT_VALUE_RE = re.compile(r"^SELECT\s+(.+?)\s+AS\s+value\b", re.IGNORECASE | re.DOTALL)


def _load_yaml(path: Path) -> tuple[dict, str | None]:
    try:
        return yaml.safe_load(path.read_text()), None
    except FileNotFoundError:
        return {}, f"Semantic layer file not found: {path}"
    except yaml.YAMLError as exc:
        return {}, f"Failed to parse semantic layer YAML: {exc}"
    except Exception as exc:
        return {}, f"Unexpected error reading semantic layer: {exc}"


def _build_group_by_sql(
    metric_sql: str,
    dim_sql: str,
    time_column: str | None,
    window: TimeWindow,
    join_overrides: dict[str, str],
) -> tuple[str, str | None]:
    """Rewrite the metric SQL as a GROUP BY query over one dimension.

    Returns (group_by_sql, error_message). Assumes metric SQL is a flat
    SELECT <agg> AS value FROM ... [WHERE ...] with no nested subqueries.
    """
    sql = metric_sql.strip()

    if time_column:
        if ":start" in sql or ":end" in sql:
            sql = sql.replace(":start", f"'{window.start}'").replace(":end", f"'{window.end}'")

    match = _SELECT_VALUE_RE.match(sql)
    if not match:
        return "", (
            "Cannot decompose: metric SQL must follow 'SELECT <agg> AS value FROM ...' pattern. "
            "Use run_sql for custom aggregations."
        )

    agg_expr = match.group(1)
    rest = sql[match.end() :]

    # Auto-inject time filter when time_column is set and the original metric SQL had no
    # :start/:end placeholders. We check `metric_sql` (the parameter), not the local `sql`
    # (which may have already had placeholders substituted away above), to avoid double-injection.
    if time_column and ":start" not in metric_sql and ":end" not in metric_sql:
        clause = f"{time_column} >= '{window.start}' AND {time_column} < '{window.end}'"
        if "WHERE" in rest.upper():
            rest = rest + f"\nAND {clause}"
        else:
            rest = rest + f"\nWHERE {clause}"

    group_sql = (
        f"SELECT ({dim_sql}) AS slice_val, {agg_expr} AS metric_value{rest}\n"
        f"GROUP BY ({dim_sql})\n"
        f"ORDER BY metric_value DESC NULLS LAST"
    )
    group_sql = _inject_joins(group_sql, dim_sql, join_overrides)
    return group_sql, None


def _anomaly_score(value: float, mean: float) -> float | None:
    if mean == 0:
        return None
    return round(abs(value - mean) / mean * 100.0, 2)


def _decompose_one_dimension(
    metric_sql: str,
    time_column: str | None,
    dim_name: str,
    dim_sql: str,
    window: TimeWindow,
    join_overrides: dict[str, str],
    conn: duckdb.DuckDBPyConnection,
) -> tuple[list[SliceResult], str | None]:
    """Run the GROUP BY query for one dimension and compute anomaly scores.

    Returns (slices, error_message).
    """
    group_sql, err = _build_group_by_sql(metric_sql, dim_sql, time_column, window, join_overrides)
    if err:
        return [], err

    try:
        rows = conn.execute(group_sql).fetchall()
    except Exception as exc:
        return [], f"SQL error decomposing by '{dim_name}': {exc}"

    values = [float(r[1]) for r in rows if r[1] is not None]
    mean = sum(values) / len(values) if values else 0.0

    slices = [
        SliceResult(
            dimension=dim_name,
            value=str(r[0]) if r[0] is not None else "NULL",
            metric_value=float(r[1]) if r[1] is not None else None,
            anomaly_score=_anomaly_score(float(r[1]), mean) if r[1] is not None else None,
        )
        for r in rows
    ]
    return slices, None


def decompose_metric(
    args: DecomposeMetricInput,
    conn: duckdb.DuckDBPyConnection | None = None,
    semantic_layer_path: str | None = None,
) -> DecomposeMetricOutput:
    """Drill down to find WHICH slice of a metric drove the movement.

    Use AFTER compare_periods has confirmed a delta. For each dimension,
    groups the metric over time_window and ranks slices by how much they
    deviate from the mean (anomaly_score). Returns all slices sorted by
    anomaly_score descending.
    All errors are returned as {error, hint} — never raised.
    """
    path = Path(
        semantic_layer_path or os.getenv(ENV_SEMANTIC_LAYER_PATH, DEFAULT_SEMANTIC_LAYER_PATH)
    )
    raw, err = _load_yaml(path)
    if err:
        return DecomposeMetricOutput(
            error=err,
            hint="Check SEMANTIC_LAYER_PATH env var or ensure data/semantic_layer.yml exists.",
        )

    metrics_raw: dict = raw.get("metrics") or {}
    dimensions_raw: dict = raw.get("dimensions") or {}
    join_overrides = _build_join_overrides(raw.get("joins") or [])

    if args.metric not in metrics_raw:
        available = list(metrics_raw.keys())
        return DecomposeMetricOutput(
            error=f"Metric {args.metric!r} not found in semantic layer.",
            hint=f"Available metrics: {available}. Call inspect_schema with no args to see all.",
        )

    # Validate all dimensions up front before running any queries.
    unknown = [d for d in args.dimensions if d not in dimensions_raw]
    if unknown:
        available = list(dimensions_raw.keys())
        return DecomposeMetricOutput(
            error=f"Unknown dimension(s): {unknown}.",
            hint=f"Available dimensions: {available}. Call inspect_schema with no args to see all.",
        )

    metric = metrics_raw[args.metric]
    metric_sql, build_err = _resolve_metric_sql(args.metric, metric)
    if build_err:
        return DecomposeMetricOutput(
            error=build_err,
            hint="Fix the semantic layer YAML or call inspect_schema to check metric definitions.",
        )

    time_column: str | None = metric.get("time_column")
    if not time_column:
        return DecomposeMetricOutput(
            error=f"Metric {args.metric!r} has no time_column and cannot be decomposed over a time window.",
            hint="Use a metric with a time_column, or call run_sql directly for a static breakdown.",
        )

    if not metric.get("decomposable", True):
        return DecomposeMetricOutput(
            error=f"Metric {args.metric!r} is marked decomposable=false (uses table aliases incompatible with GROUP BY rewrite).",
            hint="Use run_sql with an explicit GROUP BY to decompose this metric manually.",
        )

    _conn: duckdb.DuckDBPyConnection | None = None
    all_slices: list[SliceResult] = []
    try:
        _conn = (
            conn
            if conn is not None
            else build_connection(os.getenv("PARQUET_DIR", DEFAULT_PARQUET_DIR))
        )
        for dim_name in args.dimensions:
            dim_sql, dim_err = _resolve_dim_sql(dim_name, dimensions_raw[dim_name])
            if dim_err:
                return DecomposeMetricOutput(
                    error=dim_err,
                    hint="Call inspect_schema with no args to see available dimensions.",
                )
            slices, err = _decompose_one_dimension(
                metric_sql, time_column, dim_name, dim_sql, args.time_window, join_overrides, _conn
            )
            if err:
                err_lower = err.lower()
                if "binder error" in err_lower or "not found" in err_lower:
                    hint = (
                        f"Dimension '{dim_name}' references a table not in the FROM clause. "
                        "Call inspect_schema with no args to see table join relationships, "
                        "then use run_sql with an explicit JOIN instead."
                    )
                else:
                    hint = "Check the metric SQL pattern and dimension names with inspect_schema."
                return DecomposeMetricOutput(error=err, hint=hint)
            all_slices.extend(slices)
    finally:
        if conn is None and _conn is not None:
            _conn.close()

    # Sort all slices across all dimensions by anomaly_score descending.
    all_slices.sort(
        key=lambda s: s.anomaly_score if s.anomaly_score is not None else -1, reverse=True
    )

    return DecomposeMetricOutput(slices=all_slices)
