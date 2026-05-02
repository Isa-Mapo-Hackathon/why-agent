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


def _load_yaml(path: Path) -> tuple[dict, str | None]:
    try:
        return yaml.safe_load(path.read_text()), None
    except FileNotFoundError:
        return {}, f"Semantic layer file not found: {path}"
    except yaml.YAMLError as exc:
        return {}, f"Failed to parse semantic layer YAML: {exc}"
    except Exception as exc:
        return {}, f"Unexpected error reading semantic layer: {exc}"


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
        dim_sql = dimensions_raw[dim_name]["sql"]  # trusted YAML source
        conditions.append(f"{dim_sql} = ?")
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
    conn: duckdb.DuckDBPyConnection,
) -> tuple[float | None, str | None]:
    """Execute the metric SQL for one time window.

    Returns (value, error_message). value is None for NULL results.
    """
    sql = metric_sql.strip()
    params: list = []

    # Replace time placeholders (from trusted YAML, not user input).
    if time_column:
        sql = sql.replace(":start", f"'{window.start}'").replace(":end", f"'{window.end}'")

    # Inject segment conditions using parameterized values.
    if segment:
        sql, params, err = _inject_segment(sql, segment, dimensions_raw)
        if err:
            return None, err

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
    metric_sql: str = metric["sql"]
    time_column: str | None = metric.get("time_column")

    # _conn is assigned inside the try so the finally block always has it in scope.
    _conn: duckdb.DuckDBPyConnection | None = None
    try:
        _conn = (
            conn
            if conn is not None
            else build_connection(os.getenv("PARQUET_DIR", DEFAULT_PARQUET_DIR))
        )
        before_value, err = _run_metric(
            metric_sql, time_column, args.before, args.segment, dimensions_raw, _conn
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
            metric_sql, time_column, args.after, args.segment, dimensions_raw, _conn
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
