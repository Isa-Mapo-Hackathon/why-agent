"""Compare an agent-generated report against a ground-truth root cause file.

Usage examples:

  # Compare a saved report JSON against ground truth
  uv run python scripts/eval_report.py \\
      --report report.json \\
      --ground-truth docs/ground_truth_pr_spike.md

  # Run the agent in replay mode, then compare
  uv run python scripts/eval_report.py \\
      --scenario pr_spike \\
      --question "Why did PR open events spike on Jan 15?" \\
      --ground-truth docs/ground_truth_pr_spike.md

  # Save the agent report to a file for later comparison
  uv run python scripts/eval_report.py \\
      --scenario pr_spike \\
      --question "Why did PR open events spike?" \\
      --ground-truth docs/ground_truth.md \\
      --save-report reports/pr_spike_report.json

The script uses MODEL_BACKEND (and associated env vars) from .env for the
judge LLM call. Set MODEL_BACKEND=minimax for dev usage.

Exit codes: 0 = pass (score >= threshold), 1 = fail, 2 = error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()

# Project root on sys.path so agent.* imports work when run from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.client import get_llm  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

PASS_THRESHOLD = 6  # score out of 10; adjustable via --threshold

JUDGE_PROMPT = """\
You are evaluating an AI agent's investigation report against a known ground truth.

## Ground truth (the real root cause)
{ground_truth}

## Agent report
{report_text}

## Evaluation task
Score how well the agent report matches the ground truth root cause.
Return a JSON object with exactly these fields:

{{
  "root_cause_match": "yes" | "partial" | "no",
  "score": <integer 0-10>,
  "reasoning": "<2-3 sentences explaining the score>",
  "missing_elements": ["<thing the report missed>", ...],
  "false_positives": ["<incorrect claim the report made>", ...]
}}

Scoring guide:
  9-10  Correct root cause, correct dimensions/segments, correct magnitude
  7-8   Correct root cause, minor gaps in supporting evidence
  5-6   Partially correct — right area but wrong segment or magnitude
  3-4   Weak — mentioned the right dimension but wrong conclusion
  0-2   Wrong root cause entirely

Return ONLY valid JSON, no markdown fences, no extra text.
"""


def load_ground_truth(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Ground truth file not found: {path}")
    return p.read_text().strip()


def load_report_from_file(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Report JSON not found: {path}")
    data = json.loads(p.read_text())
    if "text" not in data:
        raise ValueError(f"Report JSON missing 'text' field: {path}")
    return data


def run_agent_and_get_report(scenario_id: str, question: str) -> dict:
    """Run the agent in replay mode and return final_report."""
    os.environ["MODEL_BACKEND"] = "replay"
    os.environ["REPLAY_SCENARIO_ID"] = scenario_id

    from agent.graph import build_graph
    from agent.state import InvestigationState

    logger.info("Running agent (replay mode, scenario=%s) ...", scenario_id)
    graph = build_graph()
    state = InvestigationState(user_question=question)
    result: InvestigationState = graph.invoke(state)
    if result.final_report is None:
        raise RuntimeError("Agent finished without producing a final_report.")
    return result.final_report


def call_judge(ground_truth: str, report: dict) -> dict:
    """Call the LLM judge and return the parsed eval dict."""
    report_text = report.get("text", "")
    prompt = JUDGE_PROMPT.format(
        ground_truth=ground_truth,
        report_text=report_text,
    )

    llm = get_llm()
    response = llm.invoke(
        [
            HumanMessage(content="You are a precise evaluator. Return only JSON."),
            HumanMessage(content=prompt),
        ]
    )

    raw = response.content.strip()
    # Strip markdown fences if the model added them despite instructions.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw)


def print_result(eval_result: dict, threshold: int) -> int:
    """Pretty-print the eval result. Returns exit code (0=pass, 1=fail)."""
    score = eval_result.get("score", 0)
    match = eval_result.get("root_cause_match", "unknown")
    reasoning = eval_result.get("reasoning", "")
    missing = eval_result.get("missing_elements", [])
    false_pos = eval_result.get("false_positives", [])

    passed = score >= threshold
    status = "PASS" if passed else "FAIL"

    print(f"\n{'=' * 60}")
    print(f"  Eval result: {status}")
    print(f"  Score:       {score}/10  (threshold: {threshold})")
    print(f"  Root cause:  {match}")
    print(f"{'=' * 60}")
    print(f"\nReasoning:\n  {reasoning}")

    if missing:
        print("\nMissing elements:")
        for item in missing:
            print(f"  - {item}")

    if false_pos:
        print("\nFalse positives:")
        for item in false_pos:
            print(f"  - {item}")

    print()
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--report", metavar="PATH", help="Path to a saved report JSON file.")
    source.add_argument(
        "--scenario", metavar="ID", help="Replay scenario ID (runs agent live in replay mode)."
    )

    parser.add_argument(
        "--question", metavar="TEXT", help="User question (required with --scenario)."
    )
    parser.add_argument(
        "--ground-truth",
        required=True,
        metavar="PATH",
        help="Markdown file with the known root cause.",
    )
    parser.add_argument(
        "--save-report", metavar="PATH", help="Save the agent report JSON here (optional)."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=PASS_THRESHOLD,
        metavar="N",
        help=f"Pass score (0-10, default {PASS_THRESHOLD}).",
    )

    args = parser.parse_args()

    # Load ground truth.
    try:
        ground_truth = load_ground_truth(args.ground_truth)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 2

    # Get the report.
    try:
        if args.report:
            report = load_report_from_file(args.report)
        else:
            if not args.question:
                parser.error("--question is required when using --scenario")
            report = run_agent_and_get_report(args.scenario, args.question)
    except Exception as e:
        logger.error("Failed to obtain report: %s", e)
        return 2

    # Optionally save the report.
    if args.save_report:
        out = Path(args.save_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
        logger.info("Report saved to %s", out)

    # Judge.
    try:
        eval_result = call_judge(ground_truth, report)
    except json.JSONDecodeError as e:
        logger.error("Judge returned invalid JSON: %s", e)
        return 2
    except Exception as e:
        logger.error("Judge call failed: %s", e)
        return 2

    return print_result(eval_result, args.threshold)


if __name__ == "__main__":
    sys.exit(main())
