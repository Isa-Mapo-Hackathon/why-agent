"""inspect_schema tool — describe the dataset via the semantic layer YAML.

Call with no args to list all tables, metrics, and dimensions.
Call with a table name to get columns, types, business meaning, and joins.
Never raises — all failures come back as {error, hint}.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from agent.constants import DEFAULT_SEMANTIC_LAYER_PATH, ENV_SEMANTIC_LAYER_PATH
from agent.tools.schemas import (
    ColumnInfo,
    InspectSchemaInput,
    InspectSchemaOutput,
    JoinInfo,
    TableSummary,
)

logger = logging.getLogger(__name__)


def _load_yaml(path: Path) -> tuple[dict, str | None]:
    """Return (parsed_dict, error_message). error_message is None on success."""
    try:
        return yaml.safe_load(path.read_text()), None
    except FileNotFoundError:
        return {}, f"Semantic layer file not found: {path}"
    except yaml.YAMLError as exc:
        return {}, f"Failed to parse semantic layer YAML: {exc}"
    except Exception as exc:
        return {}, f"Unexpected error reading semantic layer: {exc}"


def _build_join_info(joins_raw: list) -> list[JoinInfo]:
    result = []
    for j in joins_raw:
        if not isinstance(j, dict):
            continue
        left = j.get("left", "")
        right = j.get("right", "")
        if not left or not right:
            logger.warning("Skipping malformed join entry (missing left/right): %r", j)
            continue
        right_parts = right.split(".")
        if len(right_parts) < 2:
            logger.warning("Join entry right=%r is not in 'table.column' format; skipping.", right)
            continue
        join_kind = j.get("join_kind", "left").upper()
        right_table = right_parts[0]
        result.append(
            JoinInfo(
                left_col=left,
                right_col=right,
                join_kind=join_kind,
                sql=f"{join_kind} JOIN {right_table} ON {left} = {right}",
            )
        )
    return result


def inspect_schema(
    args: InspectSchemaInput,
    semantic_layer_path: str | None = None,
) -> InspectSchemaOutput:
    """List tables / metrics / dimensions, or describe a single table in detail.

    Call with no args first to discover what tables and metrics are available.
    Then call with table=<name> to get columns, types, and join keys before writing SQL.
    All errors are returned as {error, hint} — never raised.
    """
    path = Path(
        semantic_layer_path or os.getenv(ENV_SEMANTIC_LAYER_PATH, DEFAULT_SEMANTIC_LAYER_PATH)
    )

    raw, err = _load_yaml(path)
    if err:
        return InspectSchemaOutput(
            error=err,
            hint="Check SEMANTIC_LAYER_PATH env var or ensure data/semantic_layer.yml exists.",
        )

    # Use `or {}` — not `, {}` — so a YAML `tables: null` (None) is also caught.
    tables_raw: dict = raw.get("tables") or {}
    metrics_raw: dict = raw.get("metrics") or {}
    dimensions_raw: dict = raw.get("dimensions") or {}

    # No table arg — return the catalogue overview.
    if args.table is None:
        # Degenerate dimensions (always evaluate to one constant value in this data slice)
        # are excluded — they confuse the agent into treating them as real columns.
        usable_dims = [
            name
            for name, d in dimensions_raw.items()
            if not (isinstance(d, dict) and d.get("degenerate_in_demo"))
        ]
        joins = _build_join_info(raw.get("joins") or [])

        # Surface gotchas (critical/high only) so the plan phase sees known confounds.
        gotchas_raw = raw.get("gotchas") or []
        key_gotchas = [
            f"[{g.get('severity', 'medium').upper()}] {g['name']}: {str(g.get('description', '')).strip()}"
            for g in gotchas_raw
            if isinstance(g, dict) and g.get("severity") in ("critical", "high")
        ]

        # Generic SQL correctness rules surfaced to the model before any query is written.
        key_gotchas.extend(
            [
                "[CRITICAL] sql_verify_columns_before_writing: Always call inspect_schema(table=<name>) "
                "for every table you plan to query. Column names in the semantic layer are authoritative — "
                "do not assume columns exist based on naming conventions.",
                "[CRITICAL] sql_no_nested_aggregates: DuckDB rejects AVG(SUM(...)) and similar nesting. "
                "Use a CTE or subquery: compute inner aggregates first, then aggregate the outer result.",
                "[CRITICAL] sql_group_by_all_non_aggregates: Every column in SELECT or ORDER BY that is "
                "not wrapped in an aggregate function must appear in GROUP BY. "
                "Use ANY_VALUE(col) for columns you need to SELECT but not group on.",
            ]
        )

        # Surface per-dimension guidance so the agent knows which dimensions matter most.
        dimension_notes: dict[str, str] = {}
        for dim_name, d in dimensions_raw.items():
            if not isinstance(d, dict) or d.get("degenerate_in_demo"):
                continue
            parts: list[str] = []
            if d.get("primary_for_demo"):
                parts.append(
                    "PRIMARY DEMO DIMENSION — always check this when comparing campaigns or segments"
                )
            desc = str(d.get("description", "")).strip()
            if desc:
                parts.append(desc)
            notes = str(d.get("notes", "")).strip()
            if notes:
                parts.append(notes)
            if parts:
                dimension_notes[dim_name] = " | ".join(parts)

        return InspectSchemaOutput(
            tables=list(tables_raw.keys()),
            metrics=list(metrics_raw.keys()),
            dimensions=usable_dims,
            dimension_notes=dimension_notes or None,
            joins=joins,
            gotchas=key_gotchas or None,
        )

    # Table arg — return full column detail.
    if args.table not in tables_raw:
        available = list(tables_raw.keys())
        return InspectSchemaOutput(
            error=f"Table {args.table!r} not found in semantic layer.",
            hint=(
                f"Available tables: {available}. "
                "Call inspect_schema with no args to see the full list."
            ),
        )

    t = tables_raw[args.table]
    try:
        columns = [
            ColumnInfo(
                name=col_name,
                type=col_def.get("type", "unknown"),
                description=col_def.get("description", ""),
            )
            for col_name, col_def in (t.get("columns") or {}).items()
        ]
        return InspectSchemaOutput(
            table=TableSummary(
                name=args.table,
                description=t.get("description", ""),
                grain=t.get("grain", ""),
                primary_key=t.get("primary_key"),
                columns=columns,
                joins=t.get("joins") or [],
            )
        )
    except Exception as exc:
        logger.warning("inspect_schema failed building table %r: %s", args.table, exc)
        return InspectSchemaOutput(
            error=f"Malformed semantic layer entry for table {args.table!r}: {exc}",
            hint="Each column key must map to a dict with at least a 'type' field in the YAML.",
        )
