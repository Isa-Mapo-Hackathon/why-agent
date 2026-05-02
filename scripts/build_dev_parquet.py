"""Export tables from a local Postgres dev DB to parquet under ``data/dev/``.

The agent reads DuckDB-on-Parquet at runtime, but during development the
source of truth is whatever Postgres instance the developer has running
locally (e.g. ``postgres-mealgen``). This script bridges the two: it
ATTACHes the Postgres database via DuckDB's ``postgres`` extension and
writes one parquet file per table into ``data/dev/``.

Re-run after any schema or row change upstream.

Usage:
    uv run python scripts/build_dev_parquet.py

Required env vars (typically set in ``.env``):
    DEV_PG_DSN   libpq-style DSN, e.g.
                 ``postgresql://user:pass@localhost:5432/mealgen``
                 or ``host=localhost port=5432 dbname=mealgen user=...``

Tables exported are listed in ``DEV_TABLES`` below. Add to that tuple
when a new table needs to be available to the agent.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DEV_DIR: Path = REPO_ROOT / "data" / "dev"

DEV_TABLES: tuple[str, ...] = ("items", "item_nutrition")


def export(dsn: str, out_dir: Path, tables: tuple[str, ...]) -> dict[str, int]:
    """ATTACH a Postgres DSN via DuckDB and write one parquet per table.

    Returns a mapping of table name to row count written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL postgres")
    conn.execute("LOAD postgres")

    # ATTACH and COPY don't bind parameters; inline the literals with the
    # standard SQL single-quote escape. DSN and out_path are
    # developer-controlled (env var + repo-local path), not external input.
    conn.execute(f"ATTACH '{_sql_quote(dsn)}' AS pg (TYPE POSTGRES, READ_ONLY)")

    counts: dict[str, int] = {}
    for table in tables:
        out_path = out_dir / f"{table}.parquet"
        logger.info("Exporting public.%s -> %s", table, out_path)
        conn.execute(
            f"COPY (SELECT * FROM pg.public.{table}) "
            f"TO '{_sql_quote(str(out_path))}' (FORMAT PARQUET)"
        )
        row = conn.execute(
            "SELECT COUNT(*) FROM read_parquet(?)",
            [str(out_path)],
        ).fetchone()
        assert row is not None
        counts[table] = int(row[0])
    return counts


def _sql_quote(value: str) -> str:
    """Escape single quotes for embedding in a SQL string literal."""
    return value.replace("'", "''")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    load_dotenv()

    dsn = os.getenv("DEV_PG_DSN")
    if not dsn:
        print(
            "DEV_PG_DSN is not set. Add it to .env (see .env.example).",
            file=sys.stderr,
        )
        return 1

    counts = export(dsn, DEV_DIR, DEV_TABLES)
    for table, n in counts.items():
        rel = (DEV_DIR / f"{table}.parquet").relative_to(REPO_ROOT)
        print(f"  {table}: {n:>7,} rows -> {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
