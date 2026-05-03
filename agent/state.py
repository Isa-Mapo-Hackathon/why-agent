"""Pydantic state model for the why-agent LangGraph state machine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Phase enum — the ordered steps of the investigation loop
# ---------------------------------------------------------------------------


class Phase(StrEnum):
    PLAN = "plan"
    DECOMPOSE = "decompose"
    DRILL = "drill"
    CROSS_CHECK = "cross_check"
    CRITIQUE = "critique"
    REPORT = "report"


# ---------------------------------------------------------------------------
# Evidence record — one entry per tool call
# ---------------------------------------------------------------------------


class EvidenceEntry(BaseModel):
    phase: Phase
    tool_name: str
    args: dict[str, Any]
    output: dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# Hypothesis — one candidate explanation under active investigation
# ---------------------------------------------------------------------------


class Hypothesis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    description: str
    supporting_evidence: list[str] = Field(default_factory=list)
    weakening_evidence: list[str] = Field(default_factory=list)
    status: str = "active"


# ---------------------------------------------------------------------------
# Tool-call result — carried between LLM node and tool-executor node
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    tool_name: str
    args: dict[str, Any]
    output: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Full graph state
# ---------------------------------------------------------------------------


class InvestigationState(BaseModel):
    user_question: str = Field(
        description="Original user question, e.g. 'Why did PR activity drop on Oct 21 2018?'"
    )

    phase: Phase = Field(default=Phase.PLAN)

    evidence: list[EvidenceEntry] = Field(
        default_factory=list,
        description="Append-only log of every tool call made during this investigation.",
    )

    hypotheses: list[Hypothesis] = Field(
        default_factory=list,
        description="All hypotheses raised so far.",
    )

    active_hypothesis_id: str | None = Field(
        default=None,
        description="Which hypothesis the agent is currently drilling into.",
    )

    pending_tool_calls: list[ToolResult] = Field(
        default_factory=list,
        description="Tool calls returned by the LLM that have not been executed yet.",
    )

    messages: list[Any] = Field(default_factory=list)

    critique_passed: bool = Field(
        default=False,
        description="Set True by critique node when evidence is strong enough to report.",
    )

    retry_count: int = Field(default=0, ge=0)

    final_report: dict[str, Any] | None = Field(default=None)

    error: str | None = Field(default=None)

    def add_evidence(self, entry: EvidenceEntry) -> None:
        self.evidence.append(entry)

    def next_hypothesis_id(self) -> str:
        n = len(self.hypotheses) + 1
        return f"H{n}"
