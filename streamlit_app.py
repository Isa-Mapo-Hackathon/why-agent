"""Streamlit demo app for why-agent."""

from __future__ import annotations

import json
import logging
import os
import re

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent.graph import build_graph  # noqa: E402
from agent.state import InvestigationState  # noqa: E402

logger = logging.getLogger(__name__)

DEMO_QUESTIONS = [
    "Why did message open rate drop in the most recent campaign?",
    "Why did new customer acquisition spike in a particular month?",
    "Why is weekend engagement consistently lower than weekday?",
]

_RCA_KEYWORDS = {
    "why",
    "cause",
    "reason",
    "explain",
    "investigate",
    "dropped",
    "spiked",
    "changed",
    "moved",
    "decline",
    "increased",
    "decreased",
    "anomaly",
}


def looks_like_rca_question(question: str) -> bool:
    """Return True if the question looks like a root-cause investigation."""
    return any(kw in question.lower() for kw in _RCA_KEYWORDS)


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks that some models emit as internal reasoning."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def format_report(report: dict) -> str:
    """Convert a final_report dict to display markdown."""
    parts: list[str] = []

    text = _strip_think_tags(report.get("text") or "")
    if text:
        parts.append(text)

    n_evidence = report.get("evidence_count", 0)
    n_hyp = len(report.get("hypotheses") or [])
    parts.append(f"\n---\n*{n_evidence} tool calls · {n_hyp} hypotheses evaluated*")

    if report.get("error"):
        parts.append(f"\n> ⚠️ Note: {report['error']}")

    return "\n".join(parts)


def format_evidence(evidence: list[dict]) -> str:
    """Format evidence entries as a numbered text block."""
    if not evidence:
        return ""
    lines: list[str] = []
    for i, e in enumerate(evidence, 1):
        phase = e.get("phase", "?")
        tool = e.get("tool_name", "?")
        out = e.get("output", {})
        err_tag = " ⚠️ ERROR" if out.get("error") else ""
        snippet = json.dumps(out, default=str)[:200]
        lines.append(f"[{i}] {phase} › {tool}{err_tag}\n    {snippet}")
    return "\n\n".join(lines)


@st.cache_resource
def get_graph():
    """Build and cache the LangGraph graph across reruns."""
    return build_graph()


def run_investigation(question: str) -> tuple[dict | None, list[dict], str]:
    """Run the full investigation graph. Returns (report, evidence, error)."""
    try:
        graph = get_graph()
        state = InvestigationState(user_question=question)
        result = graph.invoke(state)

        report = result.get("final_report")
        raw_evidence = result.get("evidence") or []
        # EvidenceEntry models → plain dicts for display
        evidence = [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in raw_evidence]

        if report:
            return report, evidence, ""
        return None, evidence, result.get("error") or "No report returned."
    except Exception as exc:
        logger.exception("Investigation failed")
        return None, [], str(exc)


def main() -> None:
    st.set_page_config(
        page_title="why-agent",
        page_icon="🔍",
        layout="wide",
    )

    st.title("🔍 why-agent")
    st.caption("Ask why a metric moved — get a structured root-cause report.")

    # Sidebar: demo presets + backend info
    with st.sidebar:
        st.subheader("Demo questions")
        for q in DEMO_QUESTIONS:
            if st.button(q, use_container_width=True):
                st.session_state["pending_question"] = q

        st.divider()
        backend = os.getenv("MODEL_BACKEND", "minimax")
        parquet_dir = os.getenv("PARQUET_DIR", "data/parquet")
        st.caption(f"Backend: `{backend}`")
        st.caption(f"Data: `{parquet_dir}`")

    if "history" not in st.session_state:
        st.session_state["history"] = []

    # Pull in a preset question clicked in the sidebar
    pending = st.session_state.pop("pending_question", None)

    question = st.chat_input(
        "Why did metric X move? (e.g. 'Why did message open rate drop last campaign?')"
    )
    # Sidebar demo button wins over stale chat-input text
    question = pending or question

    if question:
        if not looks_like_rca_question(question):
            st.warning(
                "why-agent is built for root-cause questions like "
                "**'Why did message open rate drop last campaign?'** — "
                "try rephrasing with 'why', 'what caused', or describing a change.",
                icon="💡",
            )

        with st.spinner(f"Investigating: *{question}*"):
            report, evidence, err = run_investigation(question)

        st.session_state["history"].append(
            {"question": question, "report": report, "evidence": evidence, "error": err}
        )

    # Render history newest-first
    for entry in reversed(st.session_state["history"]):
        with st.chat_message("user"):
            st.write(entry["question"])

        with st.chat_message("assistant"):
            report = entry.get("report")
            if report:
                st.markdown(format_report(report))

                hypotheses = report.get("hypotheses") or []
                if hypotheses:
                    with st.expander(f"Hypotheses ({len(hypotheses)})"):
                        for h in hypotheses:
                            status = h.get("status", "active")
                            icon = "✅" if status == "confirmed" else "🔍"
                            st.markdown(
                                f"**{icon} [{h.get('id', '?')}]** {h.get('description', '')}"
                            )
                            supporting = h.get("supporting_evidence") or []
                            if supporting:
                                st.caption("Supporting: " + ", ".join(supporting))

                evidence = entry.get("evidence") or []
                if evidence:
                    with st.expander(f"Evidence trace ({len(evidence)} tool calls)"):
                        st.code(format_evidence(evidence), language=None)

            elif entry.get("error"):
                st.error(entry["error"])


if __name__ == "__main__":
    main()
