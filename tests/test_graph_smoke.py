"""Smoke tests for agent/state.py and agent/graph.py."""


from agent.graph import build_graph
from agent.state import (
    EvidenceEntry,
    Hypothesis,
    InvestigationState,
    Phase,
    ToolResult,
)


class TestPhase:
    def test_phase_values(self):
        assert Phase.PLAN.value == "plan"
        assert Phase.DECOMPOSE.value == "decompose"
        assert Phase.DRILL.value == "drill"
        assert Phase.CROSS_CHECK.value == "cross_check"
        assert Phase.CRITIQUE.value == "critique"
        assert Phase.REPORT.value == "report"


class TestInvestigationState:
    def test_default_state(self):
        state = InvestigationState(user_question="Why did X move?")
        assert state.user_question == "Why did X move?"
        assert state.phase == Phase.PLAN
        assert state.evidence == []
        assert state.hypotheses == []
        assert state.critique_passed is False
        assert state.retry_count == 0
        assert state.final_report is None

    def test_add_evidence(self):
        state = InvestigationState(user_question="test")
        entry = EvidenceEntry(
            phase=Phase.PLAN,
            tool_name="inspect_schema",
            args={},
            output={"tables": ["github_events"]},
        )
        state.add_evidence(entry)
        assert len(state.evidence) == 1
        assert state.evidence[0].tool_name == "inspect_schema"

    def test_next_hypothesis_id(self):
        state = InvestigationState(user_question="test")
        assert state.next_hypothesis_id() == "H1"
        state.hypotheses.append(Hypothesis(description="first"))
        assert state.next_hypothesis_id() == "H2"


class TestHypothesis:
    def test_default_status(self):
        h = Hypothesis(description="test hypothesis")
        assert h.status == "active"
        assert len(h.id) == 8


class TestToolResult:
    def test_tool_result_fields(self):
        tr = ToolResult(tool_name="run_sql", args={"query": "SELECT 1"}, output={})
        assert tr.tool_name == "run_sql"
        assert tr.args["query"] == "SELECT 1"


class TestGraph:
    def test_build_graph(self):
        g = build_graph()
        assert hasattr(g, "invoke"), "graph must be runnable"
        assert hasattr(g, "nodes"), "graph must have nodes"
        expected_nodes = {
            "__start__",
            "plan",
            "decompose",
            "drill",
            "cross_check",
            "llm_call",
            "execute_tools",
            "critique",
            "report",
        }
        assert set(g.nodes.keys()) == expected_nodes

    def test_state_transitions_smoke(self):
        state = InvestigationState(user_question="Why did X move?")
        assert state.phase == Phase.PLAN
        state.phase = Phase.CRITIQUE
        assert state.phase == Phase.CRITIQUE
