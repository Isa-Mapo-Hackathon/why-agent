"""Smoke tests for agent/state.py and agent/graph.py."""

from unittest.mock import MagicMock, patch

from agent.graph import MAX_RETRIES, build_graph, critique
from agent.prompts import _render_system
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
        assert state.critique_feedback is None
        assert state.pending_reasoning is None

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


# ---------------------------------------------------------------------------
# _render_system — critique_feedback injection
# ---------------------------------------------------------------------------


class TestRenderSystem:
    def test_no_feedback_renders_empty_slot(self):
        out = _render_system(
            phase="plan",
            hypotheses="No hypotheses yet.",
            evidence_summary="No evidence collected yet.",
            critique_feedback=None,
        )
        assert "VERDICT: weak" not in out
        assert "{critique_feedback}" not in out  # placeholder must be fully substituted

    def test_feedback_renders_verdict_header(self):
        out = _render_system(
            phase="decompose",
            hypotheses="H1: holiday timing.",
            evidence_summary="[plan] inspect_schema: {...}",
            critique_feedback="is_holiday_window check missing; eventually_converted not segmented.",
        )
        assert "VERDICT: weak" in out
        assert "is_holiday_window check missing" in out
        assert "close that specific gap" in out

    def test_feedback_rendered_as_blockquote(self):
        feedback = "Key evidence missing: holiday check."
        out = _render_system(
            phase="decompose",
            hypotheses="",
            evidence_summary="",
            critique_feedback=feedback,
        )
        assert f"> {feedback}" in out

    def test_empty_string_feedback_renders_no_block(self):
        out = _render_system(
            phase="plan",
            hypotheses="",
            evidence_summary="",
            critique_feedback="",
        )
        assert "VERDICT: weak" not in out

    def test_phase_substituted_correctly(self):
        out = _render_system(
            phase="cross_check",
            hypotheses="",
            evidence_summary="",
        )
        assert "cross_check" in out
        assert "{phase}" not in out  # all occurrences of the placeholder must be replaced


# ---------------------------------------------------------------------------
# critique node — feedback capture behaviour
# ---------------------------------------------------------------------------


def _make_llm_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = text
    return resp


def _blank_state() -> InvestigationState:
    return InvestigationState(user_question="Why did open rate drop?")


class TestCritiqueNode:
    def test_strong_verdict_sets_passed_and_clears_feedback(self):
        state = _blank_state()
        state.critique_feedback = "stale feedback from prior pass"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "VERDICT: strong\nEvidence is conclusive."
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is True
        assert result.critique_feedback is None

    def test_weak_verdict_captures_justification(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "VERDICT: weak\nSegment-A check missing. Metric-B not segmented."
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        mock_llm.invoke.assert_called_once()
        # user_question must appear in what was sent to the LLM
        prompt_sent = mock_llm.invoke.call_args[0][0][0].content
        assert state.user_question in prompt_sent
        assert result.critique_passed is False
        assert result.critique_feedback is not None
        assert "Segment-A check missing" in result.critique_feedback
        assert "Metric-B not segmented" in result.critique_feedback

    def test_weak_verdict_increments_retry_count_from_zero(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("VERDICT: weak\nNot enough.")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.retry_count == 1

    def test_weak_verdict_increments_retry_count_from_nonzero(self):
        state = _blank_state()
        state.retry_count = 1
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("VERDICT: weak\nStill not enough.")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.retry_count == 2

    def test_max_retries_forces_report_with_error(self):
        state = _blank_state()
        state.retry_count = MAX_RETRIES - 1
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("VERDICT: weak\nStill missing data.")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is True
        assert result.error is not None
        assert "Max critique retries" in result.error
        # critique_feedback is non-None at this point (set from the weak response before forced pass)
        assert result.critique_feedback is not None

    def test_verdict_strong_via_fallback_evidence_is_strong(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("The evidence is strong. Done.")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is True
        assert result.critique_feedback is None

    def test_verdict_strong_via_fallback_proceed_to_report(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("Proceed to report now.")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is True
        assert result.critique_feedback is None

    def test_weak_verdict_no_justification_text_sets_feedback_none(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("VERDICT: weak")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is False
        assert result.critique_feedback is None

    def test_weak_verdict_only_justification_lines_captured(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "VERDICT: weak\nLine one of justification.\nLine two of justification."
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        # First line (the VERDICT line) must not appear in feedback
        assert result.critique_feedback is not None
        assert "VERDICT" not in result.critique_feedback
        assert "Line one" in result.critique_feedback
        assert "Line two" in result.critique_feedback
