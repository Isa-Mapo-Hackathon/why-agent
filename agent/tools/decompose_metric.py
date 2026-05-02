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
) -> tuple[str, str | None]:
    """Rewrite the metric SQL as a GROUP BY query over one dimension.

    Returns (group_by_sql, error_message). Assumes metric SQL is a flat
    SELECT <agg> AS value FROM ... [WHERE ...] with no nested subqueries.
    """
    sql = metric_sql.strip()

    if time_column:
        sql = sql.replace(":start", f"'{window.start}'").replace(":end", f"'{window.end}'")

    match = _SELECT_VALUE_RE.match(sql)
    if not match:
        return "", (
            "Cannot decompose: metric SQL must follow 'SELECT <agg> AS value FROM ...' pattern. "
            "Use run_sql for custom aggregations."
        )

    agg_expr = match.group(1)
    rest = sql[match.end() :]

    group_sql = (
        f"SELECT {dim_sql} AS slice_val, {agg_expr} AS metric_value{rest}\n"
        f"GROUP BY {dim_sql}\n"
        f"ORDER BY metric_value DESC NULLS LAST"
    )
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
    conn: duckdb.DuckDBPyConnection,
) -> tuple[list[SliceResult], str | None]:
    """Run the GROUP BY query for one dimension and compute anomaly scores.

    Returns (slices, error_message).
    """
    group_sql, err = _build_group_by_sql(metric_sql, dim_sql, time_column, window)
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
    metric_sql: str | None = metric.get("sql")
    if not metric_sql:
        return DecomposeMetricOutput(
            error=f"Metric {args.metric!r} is missing 'sql' in the semantic layer.",
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
            dim_sql_raw: str | None = dimensions_raw[dim_name].get("sql")
            if not dim_sql_raw:
                return DecomposeMetricOutput(
                    error=f"Dimension {dim_name!r} is missing 'sql' in the semantic layer.",
                    hint="Fix the semantic layer YAML or call inspect_schema to check dimension definitions.",
                )
            dim_sql = dim_sql_raw
            slices, err = _decompose_one_dimension(
                metric_sql, time_column, dim_name, dim_sql, args.time_window, _conn
            )
            if err:
                return DecomposeMetricOutput(
                    error=err,
                    hint="Check the metric SQL pattern and dimension names with inspect_schema.",
                )
            all_slices.extend(slices)
    finally:
        if conn is None and _conn is not None:
            _conn.close()

    # Sort all slices across all dimensions by anomaly_score descending.
    all_slices.sort(
        key=lambda s: s.anomaly_score if s.anomaly_score is not None else -1, reverse=True
    )

    return DecomposeMetricOutput(slices=all_slices)
