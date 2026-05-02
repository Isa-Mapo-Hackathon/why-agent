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
        return InspectSchemaOutput(
            tables=list(tables_raw.keys()),
            metrics=list(metrics_raw.keys()),
            dimensions=list(dimensions_raw.keys()),
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
                name=col["name"],
                type=col["type"],
                description=col.get("description", ""),
            )
            for col in (t.get("columns") or [])
        ]
        return InspectSchemaOutput(
            table=TableSummary(
                name=args.table,
                description=t.get("description", ""),
                grain=t.get("grain", ""),
                columns=columns,
                joins=t.get("joins") or [],
            )
        )
    except Exception as exc:
        logger.warning("inspect_schema failed building table %r: %s", args.table, exc)
        return InspectSchemaOutput(
            error=f"Malformed semantic layer entry for table {args.table!r}: {exc}",
            hint="Check that every column has 'name' and 'type' fields in the YAML.",
        )
