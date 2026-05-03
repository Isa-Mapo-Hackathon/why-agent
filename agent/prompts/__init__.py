"""Prompt templates for why-agent.

SYSTEM_PROMPT — injected at every LLM turn with phase/hypotheses/evidence substituted.
CRITIQUE_PROMPT — sent to the LLM at the critique node to evaluate evidence strength.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent

_RAW_SYSTEM = (_PROMPTS_DIR / "system.md").read_text()
_RAW_CRITIQUE = (_PROMPTS_DIR / "critique.md").read_text()


def _render_system(phase: str, hypotheses: str, evidence_summary: str) -> str:
    return _RAW_SYSTEM.replace("{phase}", phase).replace("{hypotheses}", hypotheses).replace(
        "{evidence_summary}", evidence_summary
    )


def _render_critique(
    user_question: str,
    hypotheses: str,
    evidence_summary: str,
    evidence_count: int,
    retry_count: int,
    max_retries: int,
) -> str:
    return (
        _RAW_CRITIQUE.replace("{user_question}", user_question)
        .replace("{hypotheses}", hypotheses)
        .replace("{evidence_summary}", evidence_summary)
        .replace("{evidence_count}", str(evidence_count))
        .replace("{retry_count}", str(retry_count))
        .replace("{MAX_RETRIES}", str(max_retries))
    )