"""Streamlit demo app for why-agent."""

from __future__ import annotations

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
    "Why did campaign 230 underperform campaign 150? They're both bulk sale-out emails sent within a week of each other, similar volume, similar audience profile. Open rate gap: 27% vs 8%.",
    "Why did message open rate drop in the most recent campaign?",
    "Why does campaign 361 convert 60x better than campaign 296?",
    "Why is weekend engagement consistently lower than weekday?",
]


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
    """Return a plain-text summary of evidence entries (used by tests)."""
    if not evidence:
        return ""
    lines: list[str] = []
    for i, e in enumerate(evidence, 1):
        phase = e.get("phase", "?")
        tool = e.get("tool_name", "?")
        out = e.get("output", {})
        err_tag = " ⚠️" if out.get("error") else ""
        lines.append(f"[{i}] {phase} › {tool}{err_tag}")
    return "\n".join(lines)


def render_evidence(evidence: list[dict]) -> None:
    """Render evidence entries as per-call expanders with full output and reasoning."""
    if not evidence:
        return
    for i, e in enumerate(evidence, 1):
        phase = e.get("phase", "?")
        tool = e.get("tool_name", "?")
        out = e.get("output", {})
        reasoning = e.get("reasoning") or ""
        has_error = bool(out.get("error"))
        icon = "⚠️" if has_error else "✓"
        label = f"[{i}] {phase} › {tool}  {icon}"
        with st.expander(label, expanded=False):
            if reasoning:
                st.markdown(f"**Reasoning:** {reasoning}")
                st.divider()
            st.json(out)


@st.cache_resource
def get_graph():
    """Build and cache the LangGraph graph across reruns."""
    return build_graph()


def run_investigation(question: str) -> tuple[dict | None, list[dict], str]:
    """Run the full investigation graph with live progress. Returns (report, evidence, error)."""
    try:
        graph = get_graph()
        init_state = InvestigationState(user_question=question)

        final_chunk: dict | None = None
        seen_evidence = 0

        with st.status("Investigating…", expanded=True) as status:
            for chunk in graph.stream(init_state, stream_mode="values"):
                final_chunk = chunk
                evidence = chunk.get("evidence") or []
                phase = str(chunk.get("phase", "")).split(".")[-1]  # "Phase.PLAN" → "PLAN"

                for e in evidence[seen_evidence:]:
                    tool = (
                        e.get("tool_name", "?")
                        if isinstance(e, dict)
                        else getattr(e, "tool_name", "?")
                    )
                    out = e.get("output", {}) if isinstance(e, dict) else getattr(e, "output", {})
                    err = out.get("error") if isinstance(out, dict) else None
                    icon = "⚠️" if err else "✓"
                    status.write(f"{icon} `{tool}` [{phase}]")

                seen_evidence = len(evidence)

            status.update(label="Investigation complete", state="complete", expanded=False)

        if final_chunk is None:
            return None, [], "Graph returned no state."

        report = final_chunk.get("final_report")
        raw_evidence = final_chunk.get("evidence") or []
        evidence_dicts = [
            e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in raw_evidence
        ]

        if report:
            return report, evidence_dicts, ""
        return None, evidence_dicts, final_chunk.get("error") or "No report returned."
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
                        render_evidence(evidence)

            elif entry.get("error"):
                st.error(entry["error"])


if __name__ == "__main__":
    main()
