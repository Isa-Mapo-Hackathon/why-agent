"""run_sql tool — execute a read-only SELECT against DuckDB.

Use this AFTER calling inspect_schema to confirm table and column names.
Returns rows as a list of dicts, plus truncation metadata. Never raises —
all failures come back as {error, hint} so the agent can self-correct.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

import duckdb

from agent.constants import DEFAULT_PARQUET_DIR, ENV_PARQUET_DIR
from agent.tools.schemas import RunSqlInput, RunSqlOutput

logger = logging.getLogger(__name__)

# Stem must be a valid SQL identifier — prevents injection via filenames.
_SAFE_STEM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_connection(parquet_dir: str | None = None) -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with parquet files registered as views.

    Parquet files whose stems are not valid SQL identifiers are skipped with a warning.
    The view name is double-quoted; the file path is parameterized — no injection surface.
    """
    directory = Path(parquet_dir or os.getenv(ENV_PARQUET_DIR, DEFAULT_PARQUET_DIR))
    conn = duckdb.connect()
    for pq_file in sorted(directory.glob("*.parquet")):
        stem = pq_file.stem
        if not _SAFE_STEM_RE.match(stem):
            logger.warning("Skipping parquet file with unsafe stem: %r", stem)
            continue
        # DuckDB DDL doesn't support parameterized queries, so we escape
        # single quotes in the path (path comes from the local filesystem, not user input).
        safe_path = str(pq_file.resolve()).replace("'", "''")
        conn.execute(f"CREATE VIEW \"{stem}\" AS SELECT * FROM read_parquet('{safe_path}')")
        logger.debug("Registered view %r from %s", stem, pq_file)
    return conn


def _is_readonly(query: str) -> bool:
    """True only when the query is a bare SELECT or a WITH … SELECT (CTE).

    Semicolons are rejected outright — LLM-generated queries never need them,
    and they would allow multi-statement injection even though DuckDB only
    executes the first statement in a single .execute() call.
    """
    stripped = query.strip()
    if not stripped:
        return False
    if ";" in query:
        return False
    first_token = stripped.split()[0].upper()
    return first_token in {"SELECT", "WITH"}


def _execute(args: RunSqlInput, conn: duckdb.DuckDBPyConnection) -> RunSqlOutput:
    try:
        start = time.monotonic()
        cursor = conn.execute(args.query)
        # Fetch one extra row to detect truncation without loading the full result set.
        raw_rows = cursor.fetchmany(args.max_rows + 1)
        elapsed_ms = (time.monotonic() - start) * 1000.0

        truncated = len(raw_rows) > args.max_rows
        raw_rows = raw_rows[: args.max_rows]

        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in raw_rows]

        return RunSqlOutput(
            rows=rows,
            truncated=truncated,
            row_count=len(rows),
            execution_ms=round(elapsed_ms, 3),
        )
    except Exception as exc:
        logger.warning("run_sql failed: %s", exc)
        return RunSqlOutput(
            rows=[],
            truncated=False,
            row_count=0,
            execution_ms=0.0,
            error=str(exc),
            hint="Check table and column names with inspect_schema, then retry.",
        )


def run_sql(args: RunSqlInput, conn: duckdb.DuckDBPyConnection | None = None) -> RunSqlOutput:
    """Execute a read-only SELECT (or WITH … SELECT) against DuckDB.

    Call inspect_schema first to confirm table/column names.
    Returns up to max_rows rows; truncated=True signals more existed.
    All errors are returned as {error, hint} — never raised.

    Prefer injecting a shared `conn` from the graph; if omitted, a one-shot
    connection is built from PARQUET_DIR and closed after the query.
    """
    if not _is_readonly(args.query):
        return RunSqlOutput(
            rows=[],
            truncated=False,
            row_count=0,
            execution_ms=0.0,
            error="Only SELECT (or WITH … SELECT) statements are allowed. Semicolons are not permitted.",
            hint="Rewrite as a read-only SELECT. Use inspect_schema to find table/column names.",
        )

    if conn is not None:
        return _execute(args, conn)

    # One-shot path: build, query, close to avoid connection leaks.
    logger.warning("run_sql called without injected connection; prefer passing a shared conn")
    tmp = build_connection()
    try:
        return _execute(args, tmp)
    finally:
        tmp.close()
