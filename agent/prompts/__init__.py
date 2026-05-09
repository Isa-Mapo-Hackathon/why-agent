"""Prompt templates for why-agent.

SYSTEM_PROMPT — injected at every LLM turn with phase/hypotheses/evidence substituted.
CRITIQUE_PROMPT — sent to the LLM at the critique node to evaluate evidence strength.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent

_RAW_SYSTEM = (_PROMPTS_DIR / "system.md").read_text()
_RAW_CRITIQUE = (_PROMPTS_DIR / "critique.md").read_text()


def _render_system(
    phase: str,
    hypotheses: str,
    evidence_summary: str,
    critique_feedback: str | None = None,
) -> str:
    feedback_block = (
        f"\n**Critique feedback (previous pass was VERDICT: weak):**\n"
        f"> {critique_feedback}\n"
        f"Your priority this pass is to close that specific gap.\n"
        if critique_feedback
        else ""
    )
    return (
        _RAW_SYSTEM.replace("{phase}", phase)
        .replace("{hypotheses}", hypotheses)
        .replace("{evidence_summary}", evidence_summary)
        .replace("{critique_feedback}", feedback_block)
    )


_EXPLORATORY_CHECKS = """\
### Required checks for EXPLORATORY questions

1. **The question is directly answered.** At least one tool call returned a
   value that responds to the user's question. If the evidence only inspects
   schema without returning the actual answer, return weak.

2. **The answer is internally consistent.** No contradictions between tool
   outputs (e.g., two COUNT queries returning wildly different totals for the
   same thing).
"""

_COMPARISON_CHECKS = """\
### Required checks for CROSS-SECTIONAL and TIME-SERIES questions

1. **Headline numbers exist.** Both sides of any comparison must have been
   measured (A and B, before and after). If either side is missing, return weak.

2. **The leading hypothesis is supported by at least one direct data point.**
   The conclusion should be grounded in something observed in the data, not
   pure inference.

3. **At least one alternative explanation was considered.** It doesn't need
   to be exhaustively ruled out — acknowledging it and providing a reason to
   favour the leading hypothesis is sufficient.
"""


def _render_critique(
    user_question: str,
    hypotheses: str,
    evidence_summary: str,
    evidence_count: int,
    retry_count: int,
    max_retries: int,
    question_type: str | None = None,
) -> str:
    checks = _EXPLORATORY_CHECKS if question_type == "EXPLORATORY" else _COMPARISON_CHECKS
    return (
        _RAW_CRITIQUE.replace("{user_question}", user_question)
        .replace("{hypotheses}", hypotheses)
        .replace("{evidence_summary}", evidence_summary)
        .replace("{evidence_count}", str(evidence_count))
        .replace("{retry_count}", str(retry_count))
        .replace("{MAX_RETRIES}", str(max_retries))
        .replace("{question_type_checks}", checks)
    )
