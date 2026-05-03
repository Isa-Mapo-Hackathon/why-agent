"""Local REPL for testing the LangGraph state machine end-to-end.

Wires build_graph() into a simple input loop so you can ask investigation
questions and watch the full 6-phase loop run.

Usage:
    PARQUET_DIR=data/dev MODEL_BACKEND=minimax uv run python scripts/repl_graph.py
    MODEL_BACKEND=replay REPLAY_SCENARIO_ID=<id> uv run python scripts/repl_graph.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv

with warnings.catch_warnings():
    warnings.simplefilter("ignore")

load_dotenv()

# Repo root so imports work when run from any directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.graph import build_graph  # noqa: E402
from agent.state import InvestigationState  # noqa: E402


def run_investigation(question: str) -> dict:
    """Run a full investigation and return the final report."""
    initial_state = InvestigationState(user_question=question)
    graph = build_graph()
    result = graph.invoke(initial_state)
    return result.get("final_report") or {"error": result.get("error", "no report returned")}


def repl() -> None:
    print("why-agent REPL — type your RCA question (Ctrl-C to quit)\n")
    graph = build_graph()
    print(f"Graph loaded. Nodes: {list(graph.nodes.keys())}\n")

    while True:
        try:
            q = input("Q: ").strip()
            if not q:
                continue
            print(f"\n{'=' * 60}")
            print(f"Investigating: {q}")
            print("=" * 60)

            initial_state = InvestigationState(user_question=q)
            result = graph.invoke(initial_state)
            report = result.get("final_report")

            if report:
                print("\n--- REPORT ---")
                print(f"Question: {report.get('user_question')}")
                print(f"\n{report.get('text', 'no text')}")
                print(f"\nevidence_count: {report.get('evidence_count')}")
                print(f"hypotheses: {len(report.get('hypotheses', []))}")
                if report.get("error"):
                    print(f"error: {report.get('error')}")
            else:
                print(f"\nNo report returned. error={result.get('error')}")
            print()

        except KeyboardInterrupt:
            print("\nbye")
            break


if __name__ == "__main__":
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        result = run_investigation(question)
        print(result)
    else:
        repl()
