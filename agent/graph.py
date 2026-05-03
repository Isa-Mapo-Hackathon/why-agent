"""LangGraph state machine for why-agent root-cause investigation.

The graph orchestrates the six-phase loop:
    plan → decompose → drill → cross_check → critique → report
                                                 ↑          |
                                                 └──────────┘ (if evidence weak)
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, StateGraph

from agent.client import get_llm
from agent.prompts import _render_critique, _render_system
from agent.state import (
    EvidenceEntry,
    Hypothesis,
    InvestigationState,
    Phase,
    ToolResult,
)
from agent.tools.schemas import (
    ComparePeriodsInput,
    DecomposeMetricInput,
    InspectSchemaInput,
    RunSqlInput,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _format_hypotheses(hypotheses: list[Hypothesis]) -> str:
    if not hypotheses:
        return "No hypotheses yet."
    lines = []
    for h in hypotheses:
        ev = ", ".join(h.supporting_evidence) or "none"
        lines.append(f"  [{h.id}] {h.description} (status={h.status}, supporting_evidence={ev})")
    return "\n".join(lines)


def _format_evidence(evidence: list[EvidenceEntry]) -> str:
    if not evidence:
        return "No evidence collected yet."
    lines = []
    for e in evidence:
        err_tag = " [ERROR]" if "error" in e.output else ""
        out_snippet = str(e.output)[:120]
        lines.append(f"  [{e.phase.value}] {e.tool_name}{err_tag}: {out_snippet}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool wrappers — each manages its own DuckDB connection so StructuredTool
# schema generation (which inspects function signatures) never sees conn
# ---------------------------------------------------------------------------

def _make_tool_wrapper(name: str):
    def wrapper(args: InspectSchemaInput | RunSqlInput | ComparePeriodsInput | DecomposeMetricInput):
        from agent.tools.run_sql import build_connection

        conn = build_connection(os.getenv("PARQUET_DIR", "data/parquet"))
        try:
            if name == "inspect_schema":
                from agent.tools.inspect_schema import inspect_schema as _fn
                return _fn(args).model_dump()  # type: ignore[arg-type]
            elif name == "run_sql":
                from agent.tools.run_sql import run_sql as _fn
                return _fn(args, conn).model_dump()  # type: ignore[arg-type]
            elif name == "compare_periods":
                from agent.tools.compare_periods import compare_periods as _fn
                return _fn(args, conn).model_dump()  # type: ignore[arg-type]
            elif name == "decompose_metric":
                from agent.tools.decompose_metric import decompose_metric as _fn
                return _fn(args, conn).model_dump()  # type: ignore[arg-type]
        finally:
            conn.close()
    return wrapper


# ---------------------------------------------------------------------------
# Cached tool definitions — built once so the LLM sees stable schemas
# ---------------------------------------------------------------------------

_CACHED_TOOLS: list[StructuredTool] | None = None


def _get_tools():  # type: ignore[reportReturnType]
    global _CACHED_TOOLS
    if _CACHED_TOOLS is None:
        _CACHED_TOOLS = [
            StructuredTool.from_function(
                name="inspect_schema",
                func=_make_tool_wrapper("inspect_schema"),
                args_schema=InspectSchemaInput,
                description="List tables (no arg) or describe one table (cols, types, business meaning).",
            ),
            StructuredTool.from_function(
                name="run_sql",
                func=_make_tool_wrapper("run_sql"),
                args_schema=RunSqlInput,
                description="Execute a read-only SELECT against DuckDB. Returns {rows, truncated, row_count, execution_ms}.",
            ),
            StructuredTool.from_function(
                name="compare_periods",
                func=_make_tool_wrapper("compare_periods"),
                args_schema=ComparePeriodsInput,
                description="Headline diff: by how much did metric change between two windows? Returns {before_value, after_value, abs_delta, pct_delta}.",
            ),
            StructuredTool.from_function(
                name="decompose_metric",
                func=_make_tool_wrapper("decompose_metric"),
                args_schema=DecomposeMetricInput,
                description="Drill-down: WHICH slice of metric drove the movement? Returns ranked slices by anomaly score.",
            ),
        ]
    return _CACHED_TOOLS


# ---------------------------------------------------------------------------
# Tool executor node
# ---------------------------------------------------------------------------

def execute_tools(state: InvestigationState) -> InvestigationState:
    """Run every pending tool call and append an EvidenceEntry for each."""
    if not state.pending_tool_calls:
        return state

    from agent.tools.run_sql import build_connection

    conn = build_connection(os.getenv("PARQUET_DIR", "data/parquet"))
    try:
        for tc in state.pending_tool_calls:
            args = tc.args
            tool_name = tc.tool_name
            output: dict = {}
            try:
                if tool_name == "inspect_schema":
                    from agent.tools.inspect_schema import inspect_schema as _fn
                    inp = InspectSchemaInput(**args)
                    output = _fn(inp).model_dump()
                elif tool_name == "run_sql":
                    from agent.tools.run_sql import run_sql as _fn
                    inp = RunSqlInput(**args)
                    output = _fn(inp, conn).model_dump()
                elif tool_name == "compare_periods":
                    from agent.tools.compare_periods import compare_periods as _fn
                    inp = ComparePeriodsInput(**args)
                    output = _fn(inp, conn).model_dump()
                elif tool_name == "decompose_metric":
                    from agent.tools.decompose_metric import decompose_metric as _fn
                    inp = DecomposeMetricInput(**args)
                    output = _fn(inp, conn).model_dump()
                else:
                    output = {
                        "error": f"Unknown tool {tool_name!r}",
                        "hint": "Use one of: inspect_schema, run_sql, compare_periods, decompose_metric.",
                    }
            except Exception as exc:
                logger.warning("Tool %s raised (converted to dict): %s", tool_name, exc)
                output = {"error": str(exc), "hint": "Retry with corrected arguments."}

            # Add ToolMessage so the LLM sees the result in the next turn.
            from langchain_core.messages import ToolMessage
            tc.output = output
            state.messages.append(
                ToolMessage(
                    content=str(output),
                    tool_call_id=tc.args.get("_tool_call_id", ""),
                )
            )

            entry = EvidenceEntry(
                phase=state.phase,
                tool_name=tool_name,
                args=args,
                output=output,
                timestamp=_iso_now(),
            )
            state.add_evidence(entry)

        state.pending_tool_calls = []
        return state
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# LLM call node
# ---------------------------------------------------------------------------

def llm_call(state: InvestigationState) -> InvestigationState:
    """Send messages to the LLM; collect tool calls into pending_tool_calls."""
    llm = get_llm()

    system_content = _render_system(
        phase=state.phase.value,
        hypotheses=_format_hypotheses(state.hypotheses),
        evidence_summary=_format_evidence(state.evidence),
    )

    all_messages = [SystemMessage(content=system_content)] + list(state.messages)
    if not any(isinstance(m, HumanMessage) for m in all_messages):
        all_messages.append(HumanMessage(content=state.user_question))
    response = llm.bind_tools(_get_tools()).invoke(all_messages)

    state.messages.append(response)

    pending: list[ToolResult] = []
    for tc in response.tool_calls or []:
        pending.append(ToolResult(
            tool_name=tc["name"],
            args={**tc["args"], "_tool_call_id": tc.get("id", "")},
            output={},
        ))
    state.pending_tool_calls = pending

    return state


# ---------------------------------------------------------------------------
# Phase-stepping nodes
# ---------------------------------------------------------------------------

def _make_phase_node(phase: Phase):
    def node(state: InvestigationState) -> InvestigationState:
        state.phase = phase
        return llm_call(state)
    return node


# ---------------------------------------------------------------------------
# Critique node
# ---------------------------------------------------------------------------

def critique(state: InvestigationState) -> InvestigationState:
    """Ask the LLM to evaluate evidence strength; decide loop or report."""
    critique_prompt = _render_critique(
        user_question=state.user_question,
        hypotheses=_format_hypotheses(state.hypotheses),
        evidence_summary=_format_evidence(state.evidence),
        evidence_count=len(state.evidence),
        retry_count=state.retry_count,
        max_retries=MAX_RETRIES,
    )

    llm = get_llm()
    response = llm.invoke([HumanMessage(content=critique_prompt)])

    text = response.content if isinstance(response.content, str) else str(response.content)
    text_lower = text.lower().strip()
    first_line = text_lower.split("\n")[0]
    if first_line.startswith("verdict:") and "strong" in first_line:
        state.critique_passed = True
    elif "evidence is strong" in text_lower or "proceed to report" in text_lower:
        state.critique_passed = True
    else:
        state.critique_passed = False
        state.retry_count += 1
        if state.retry_count >= MAX_RETRIES:
            logger.warning("Max critique retries (%d) reached; forcing report.", MAX_RETRIES)
            state.critique_passed = True
            state.error = "Max critique retries reached. Evidence may be incomplete."

    return state


# ---------------------------------------------------------------------------
# Report node
# ---------------------------------------------------------------------------

def report(state: InvestigationState) -> InvestigationState:
    """Assemble and store the final report dict."""
    report_prompt = (
        f"Based on the investigation of: {state.user_question}\n\n"
        f"Hypotheses considered:\n{_format_hypotheses(state.hypotheses)}\n\n"
        f"Evidence:\n{_format_evidence(state.evidence)}\n\n"
        f"Write a concise structured report with: root_cause, supporting_evidence (by hypothesis id), "
        f"confidence (high/medium/low), and next_steps (what would confirm this)."
    )

    llm = get_llm()
    # MiniMax rejects single HumanMessage; prepend a dummy HumanMessage to keep it happy.
    response = llm.invoke([HumanMessage(content="Please answer."), HumanMessage(content=report_prompt)])

    state.final_report = {
        "user_question": state.user_question,
        "text": response.content,
        "hypotheses": [h.model_dump() for h in state.hypotheses],
        "evidence_count": len(state.evidence),
        "critique_passed": state.critique_passed,
        "error": state.error,
    }
    return state


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph():
    builder = StateGraph(InvestigationState)

    builder.add_node("llm_call", llm_call)
    builder.add_node("execute_tools", execute_tools)
    builder.add_node("critique", critique)
    builder.add_node("report", report)

    for phase in [Phase.PLAN, Phase.DECOMPOSE, Phase.DRILL, Phase.CROSS_CHECK]:
        builder.add_node(phase.value, _make_phase_node(phase))

    def route_after_llm(state: InvestigationState) -> Literal["execute_tools", "critique"]:
        return "execute_tools" if state.pending_tool_calls else "critique"

    for phase in [Phase.PLAN, Phase.DECOMPOSE, Phase.DRILL, Phase.CROSS_CHECK]:
        builder.add_conditional_edges(phase.value, route_after_llm)

    builder.add_edge("execute_tools", "llm_call")
    builder.add_conditional_edges("llm_call", route_after_llm)

    def route_after_critique(state: InvestigationState) -> Literal["report", "decompose"]:
        return "report" if state.critique_passed else "decompose"

    builder.add_conditional_edges("critique", route_after_critique)
    builder.add_edge("report", END)

    builder.set_entry_point("plan")

    return builder.compile()