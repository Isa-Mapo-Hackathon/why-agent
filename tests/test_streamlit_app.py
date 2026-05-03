"""Tests for streamlit_app.py business logic and UI smoke."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_renders_text(self):
        from streamlit_app import format_report

        report = {
            "text": "Root cause: platform outage at 3 PM.",
            "evidence_count": 5,
            "hypotheses": [],
            "error": None,
        }
        out = format_report(report)
        assert "Root cause: platform outage at 3 PM." in out

    def test_includes_evidence_count(self):
        from streamlit_app import format_report

        report = {"text": "analysis", "evidence_count": 7, "hypotheses": [], "error": None}
        out = format_report(report)
        assert "7" in out

    def test_includes_hypothesis_count(self):
        from streamlit_app import format_report

        report = {
            "text": "analysis",
            "evidence_count": 3,
            "hypotheses": [{"id": "H1"}, {"id": "H2"}],
            "error": None,
        }
        out = format_report(report)
        assert "2" in out

    def test_shows_error_note_when_present(self):
        from streamlit_app import format_report

        report = {
            "text": "partial analysis",
            "evidence_count": 2,
            "hypotheses": [],
            "error": "Max critique retries reached.",
        }
        out = format_report(report)
        assert "Max critique retries reached." in out

    def test_no_error_note_when_absent(self):
        from streamlit_app import format_report

        report = {"text": "clean", "evidence_count": 1, "hypotheses": [], "error": None}
        out = format_report(report)
        assert "Note:" not in out


# ---------------------------------------------------------------------------
# format_evidence
# ---------------------------------------------------------------------------


class TestFormatEvidence:
    def test_empty_returns_empty_string(self):
        from streamlit_app import format_evidence

        assert format_evidence([]) == ""

    def test_includes_tool_name(self):
        from streamlit_app import format_evidence

        evidence = [
            {
                "phase": "plan",
                "tool_name": "inspect_schema",
                "args": {},
                "output": {"tables": ["t1"]},
            }
        ]
        out = format_evidence(evidence)
        assert "inspect_schema" in out

    def test_includes_phase(self):
        from streamlit_app import format_evidence

        evidence = [
            {
                "phase": "decompose",
                "tool_name": "compare_periods",
                "args": {},
                "output": {"abs_delta": 10},
            }
        ]
        out = format_evidence(evidence)
        assert "decompose" in out

    def test_marks_error_entries(self):
        from streamlit_app import format_evidence

        evidence = [
            {"phase": "drill", "tool_name": "run_sql", "args": {}, "output": {"error": "bad query"}}
        ]
        out = format_evidence(evidence)
        assert "ERROR" in out.upper()

    def test_multiple_entries_numbered(self):
        from streamlit_app import format_evidence

        evidence = [
            {"phase": "plan", "tool_name": "inspect_schema", "args": {}, "output": {}},
            {"phase": "decompose", "tool_name": "run_sql", "args": {}, "output": {}},
        ]
        out = format_evidence(evidence)
        assert "[1]" in out
        assert "[2]" in out


# ---------------------------------------------------------------------------
# run_investigation
# ---------------------------------------------------------------------------


class TestRunInvestigation:
    def test_returns_report_on_success(self):
        from streamlit_app import run_investigation

        fake_report = {
            "user_question": "Why?",
            "text": "Because X.",
            "hypotheses": [],
            "evidence_count": 2,
            "error": None,
        }
        fake_result = {"final_report": fake_report, "evidence": []}

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = fake_result

        with patch("streamlit_app.get_graph", return_value=mock_graph):
            report, evidence, err = run_investigation("Why?")

        assert report == fake_report
        assert err == ""

    def test_returns_error_string_when_no_report(self):
        from streamlit_app import run_investigation

        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "final_report": None,
            "error": "graph blew up",
            "evidence": [],
        }

        with patch("streamlit_app.get_graph", return_value=mock_graph):
            report, evidence, err = run_investigation("Why?")

        assert report is None
        assert "graph blew up" in err

    def test_returns_error_string_on_exception(self):
        from streamlit_app import run_investigation

        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("connection refused")

        with patch("streamlit_app.get_graph", return_value=mock_graph):
            report, evidence, err = run_investigation("Why?")

        assert report is None
        assert "connection refused" in err

    def test_passes_evidence_from_state(self):
        from streamlit_app import run_investigation

        ev = [{"phase": "plan", "tool_name": "inspect_schema", "args": {}, "output": {}}]
        fake_result = {
            "final_report": {"text": "ok", "hypotheses": [], "evidence_count": 1, "error": None},
            "evidence": ev,
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = fake_result

        with patch("streamlit_app.get_graph", return_value=mock_graph):
            _, evidence, _ = run_investigation("Why?")

        assert len(evidence) == 1
        assert evidence[0]["tool_name"] == "inspect_schema"


# ---------------------------------------------------------------------------
# AppTest smoke — just verify the app renders without crashing
# ---------------------------------------------------------------------------


class TestAppSmoke:
    def test_app_renders_without_exception(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("streamlit_app.py", default_timeout=10)
        at.run()
        assert not at.exception, f"App raised: {at.exception}"

    def test_app_has_chat_input(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("streamlit_app.py", default_timeout=10)
        at.run()
        assert len(at.chat_input) >= 1
