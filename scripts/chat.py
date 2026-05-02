"""Quick end-to-end chat script for testing the agent locally.

Wires run_sql to a LangGraph ReAct agent with the semantic layer as context.
Uses MODEL_BACKEND / MINIMAX_API_KEY from .env (or environment).

Usage:
    PARQUET_DIR=data/dev uv run python scripts/chat.py
"""

import os
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from langgraph.prebuilt import create_react_agent

load_dotenv()

# Repo root so imports work when run from any directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.client import get_llm  # noqa: E402
from agent.tools.inspect_schema import inspect_schema  # noqa: E402
from agent.tools.run_sql import build_connection, run_sql  # noqa: E402
from agent.tools.schemas import InspectSchemaInput, RunSqlInput  # noqa: E402

SEMANTIC_LAYER_PATH = os.getenv("SEMANTIC_LAYER_PATH", "data/semantic_layer.yml")
PARQUET_DIR = os.getenv("PARQUET_DIR", "data/parquet")

_sl_path = SEMANTIC_LAYER_PATH
_semantic_layer = Path(SEMANTIC_LAYER_PATH).read_text()
_conn = build_connection(PARQUET_DIR)


@tool
def inspect_schema_tool(table: str | None = None) -> dict:
    """List all tables / metrics / dimensions (no arg), or describe one table's columns and joins.

    Always call this first — before run_sql — to confirm table and column names.
    Returns: {tables, metrics, dimensions} overview or {table: {columns, joins}} detail.
    """
    result = inspect_schema(InspectSchemaInput(table=table), _sl_path)
    return result.model_dump()


@tool
def run_sql_tool(query: str, max_rows: int = 100) -> dict:
    """Execute a read-only SELECT (or WITH … SELECT) against DuckDB.

    Call this to answer quantitative questions about the dataset.
    Returns: {rows, truncated, row_count, execution_ms} on success,
             {error, hint} on failure — use the hint to self-correct.
    """
    result = run_sql(RunSqlInput(query=query, max_rows=max_rows), _conn)
    return result.model_dump()


SYSTEM_PROMPT = f"""You are a data analyst agent. You answer questions by querying a DuckDB database.

Always use run_sql_tool to fetch data before answering. Do not guess values.

## Semantic layer (schema + business context)

{_semantic_layer}
"""

llm = get_llm()
agent = create_react_agent(llm, tools=[inspect_schema_tool, run_sql_tool], prompt=SYSTEM_PROMPT)


def chat(question: str) -> None:
    print(f"\nQ: {question}")
    print("-" * 60)
    result = agent.invoke({"messages": [("human", question)]})
    print(result["messages"][-1].content)
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        chat(" ".join(sys.argv[1:]))
    else:
        print("Type your question (Ctrl-C to quit):\n")
        while True:
            try:
                q = input("> ").strip()
                if q:
                    chat(q)
            except KeyboardInterrupt:
                break
