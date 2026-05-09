"""Smoke tests for agent/state.py and agent/graph.py."""

from unittest.mock import MagicMock, patch

from agent.graph import MAX_RETRIES, build_graph, critique, llm_call, report
from agent.prompts import _render_critique, _render_system
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
        assert state.question_type is None

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
    def test_sets_phase_to_critique(self):
        state = _blank_state()
        state.phase = Phase.CROSS_CHECK
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "VERDICT: strong\nEvidence is conclusive."
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.phase == Phase.CRITIQUE

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

    def test_inline_verdict_weak_captured(self):
        """VERDICT: weak embedded mid-line (not line-initial) must still be parsed."""
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "After review, VERDICT: weak — the after-period is missing."
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is False

    def test_inline_verdict_strong_captured(self):
        """VERDICT: strong embedded mid-line must still be parsed."""
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "Based on the evidence, VERDICT: strong — answer is complete."
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is True

    def test_no_verdict_no_fallback_increments_retry(self):
        """No VERDICT line and no fallback keyword → retry incremented, feedback None."""
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "The data supports the hypothesis partially."
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is False
        assert result.critique_feedback is None
        assert result.retry_count == 1

    def test_fallback_strong_requires_line_start_not_mid_sentence(self):
        """'evidence is strong' mid-sentence must NOT trigger the fallback."""
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "While the evidence is strong for the headline metric, the after-period is missing.\n"
            "VERDICT: weak"
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        # The VERDICT: weak line takes priority; fallback must NOT override it
        assert result.critique_passed is False

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


class TestReportNode:
    def test_sets_phase_to_report(self):
        state = _blank_state()
        state.phase = Phase.CRITIQUE
        state.critique_passed = True
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("Final report.")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = report(state)
        assert result.phase == Phase.REPORT
        assert result.final_report is not None


# ---------------------------------------------------------------------------
# Fix 2 — <think> tag stripping in critique parser
# ---------------------------------------------------------------------------


class TestCritiqueThinkTagStripping:
    """VERDICT buried inside <think> tags must still be parsed correctly."""

    def test_verdict_strong_inside_think_block(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "<think>\nVERDICT: strong\nEvidence is sufficient.\n</think>"
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is True
        assert result.critique_feedback is None

    def test_verdict_weak_inside_think_block(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "<think>\nVERDICT: weak\nMissing comparison data.\n</think>"
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is False

    def test_verdict_strong_after_think_block(self):
        state = _blank_state()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(
            "<think>thinking...</think>\nVERDICT: strong\nGood evidence."
        )
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = critique(state)
        assert result.critique_passed is True


# ---------------------------------------------------------------------------
# Fix 1a — question_type field on InvestigationState
# ---------------------------------------------------------------------------


class TestQuestionTypeField:
    def test_default_is_none(self):
        state = InvestigationState(user_question="How many campaigns?")
        assert state.question_type is None

    def test_can_be_set_on_construction(self):
        state = InvestigationState(user_question="How many campaigns?", question_type="EXPLORATORY")
        assert state.question_type == "EXPLORATORY"

    def test_can_be_set_after_construction(self):
        state = InvestigationState(user_question="How many campaigns?")
        state.question_type = "TIME_SERIES"
        assert state.question_type == "TIME_SERIES"


# ---------------------------------------------------------------------------
# Fix 1b — plan phase captures question_type from LLM reasoning
# ---------------------------------------------------------------------------


def _mock_plan_llm(classification: str) -> MagicMock:
    """Return a mock LLM whose plan-phase response contains the given classification keyword."""
    resp = MagicMock()
    resp.content = f"This is a {classification} question. Let me inspect the schema."
    resp.tool_calls = []
    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.invoke.return_value = resp
    return mock_llm


class TestPlanPhaseCapture:
    def test_exploratory_classification_captured(self):
        state = InvestigationState(user_question="How many campaigns are there?")
        state.phase = Phase.PLAN
        with patch("agent.graph.get_llm", return_value=_mock_plan_llm("EXPLORATORY")):
            result = llm_call(state)
        assert result.question_type == "EXPLORATORY"

    def test_cross_sectional_classification_captured(self):
        state = InvestigationState(user_question="Why does campaign A outperform B?")
        state.phase = Phase.PLAN
        with patch("agent.graph.get_llm", return_value=_mock_plan_llm("CROSS-SECTIONAL")):
            result = llm_call(state)
        assert result.question_type == "CROSS_SECTIONAL"

    def test_time_series_classification_captured(self):
        state = InvestigationState(user_question="Why did open rate drop in June?")
        state.phase = Phase.PLAN
        with patch("agent.graph.get_llm", return_value=_mock_plan_llm("TIME-SERIES")):
            result = llm_call(state)
        assert result.question_type == "TIME_SERIES"

    def test_no_classification_leaves_none(self):
        state = InvestigationState(user_question="test")
        state.phase = Phase.PLAN
        mock_llm = _mock_plan_llm("")  # no keyword in response
        mock_llm.invoke.return_value.content = "Let me look at the data."
        with patch("agent.graph.get_llm", return_value=mock_llm):
            result = llm_call(state)
        assert result.question_type is None

    def test_non_plan_phase_does_not_overwrite(self):
        state = InvestigationState(user_question="test", question_type="EXPLORATORY")
        state.phase = Phase.DECOMPOSE  # not PLAN
        with patch("agent.graph.get_llm", return_value=_mock_plan_llm("TIME-SERIES")):
            result = llm_call(state)
        assert result.question_type == "EXPLORATORY"  # untouched


# ---------------------------------------------------------------------------
# Fix 1c — _render_critique generates question-type-specific required checks
# ---------------------------------------------------------------------------


class TestRenderCritiqueQuestionType:
    def _render(self, question_type: str | None) -> str:
        return _render_critique(
            user_question="test question",
            hypotheses="No hypotheses.",
            evidence_summary="Some evidence.",
            evidence_count=2,
            retry_count=0,
            max_retries=2,
            question_type=question_type,
        )

    def test_exploratory_contains_direct_answer_check(self):
        out = self._render("EXPLORATORY")
        assert "directly answered" in out.lower()

    def test_exploratory_omits_both_sides_check(self):
        out = self._render("EXPLORATORY")
        assert "both sides" not in out.lower()

    def test_comparison_contains_both_sides_check(self):
        out = self._render("CROSS_SECTIONAL")
        assert "both sides" in out.lower()

    def test_time_series_contains_both_sides_check(self):
        out = self._render("TIME_SERIES")
        assert "both sides" in out.lower()

    def test_none_type_falls_back_to_comparison_checks(self):
        out = self._render(None)
        assert "both sides" in out.lower()


# ---------------------------------------------------------------------------
# Fix 1d — critique node passes question_type to prompt when set
# ---------------------------------------------------------------------------


class TestCritiqueUsesQuestionType:
    def test_exploratory_state_sends_exploratory_guidance_in_prompt(self):
        state = _blank_state()
        state.question_type = "EXPLORATORY"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("VERDICT: strong\nDirect answer found.")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            critique(state)
        prompt_sent = mock_llm.invoke.call_args[0][0][0].content
        assert "directly answered" in prompt_sent.lower()

    def test_cross_sectional_state_sends_comparison_guidance_in_prompt(self):
        state = _blank_state()
        state.question_type = "CROSS_SECTIONAL"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response("VERDICT: strong\nBoth sides measured.")
        with patch("agent.graph.get_llm", return_value=mock_llm):
            critique(state)
        prompt_sent = mock_llm.invoke.call_args[0][0][0].content
        assert "both sides" in prompt_sent.lower()
