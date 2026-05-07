"""Smoke tests for the FastAPI backend. All tests use a fake graph — no LLM, no network."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

os.environ.setdefault("MODEL_BACKEND", "replay")

from client.backend.main import app  # noqa: E402


class _FakeGraph:
    """Minimal graph stub that yields predictable state chunks then a final report."""

    def stream(self, init_state, stream_mode="values") -> Iterator[dict]:
        from agent.state import EvidenceEntry, Phase

        yield {
            "phase": Phase.PLAN,
            "evidence": [],
            "hypotheses": [],
            "retry_count": 0,
            "final_report": None,
        }
        yield {
            "phase": Phase.DECOMPOSE,
            "evidence": [
                EvidenceEntry(
                    phase=Phase.DECOMPOSE,
                    tool_name="run_sql",
                    args={"query": "SELECT 1", "max_rows": 10},
                    output={
                        "rows": [{"1": 1}],
                        "row_count": 1,
                        "truncated": False,
                        "execution_ms": 5.0,
                    },
                )
            ],
            "hypotheses": [],
            "retry_count": 0,
            "final_report": None,
        }
        yield {
            "phase": Phase.REPORT,
            "evidence": [
                EvidenceEntry(
                    phase=Phase.DECOMPOSE,
                    tool_name="run_sql",
                    args={"query": "SELECT 1", "max_rows": 10},
                    output={
                        "rows": [{"1": 1}],
                        "row_count": 1,
                        "truncated": False,
                        "execution_ms": 5.0,
                    },
                )
            ],
            "hypotheses": [],
            "retry_count": 0,
            "final_report": {
                "user_question": "test question",
                "text": "Test report text.",
                "hypotheses": [],
                "evidence_count": 1,
                "critique_passed": True,
                "error": None,
            },
        }


def _parse_sse(lines: Iterator[str]) -> list[dict]:
    """Parse raw SSE text lines into a list of {event, data} dicts."""
    events: list[dict] = []
    current: dict = {}
    for line in lines:
        if line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            raw = line[5:].strip()
            try:
                current["data"] = json.loads(raw)
            except json.JSONDecodeError:
                current["data"] = raw
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


@pytest.fixture(autouse=True)
def _clear_graph_cache():
    from client.backend.deps import get_graph

    get_graph.cache_clear()
    yield
    get_graph.cache_clear()


@pytest.fixture()
def client():
    with patch("client.backend.deps.build_graph", return_value=_FakeGraph()):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_demo_questions(client):
    r = client.get("/api/demo-questions")
    assert r.status_code == 200
    data = r.json()
    assert "questions" in data
    assert len(data["questions"]) == 4
    assert all(isinstance(q, str) for q in data["questions"])


def test_investigate_empty_question_rejected(client):
    r = client.post("/api/investigate", json={"question": ""})
    assert r.status_code == 422


def test_investigate_missing_question_rejected(client):
    r = client.post("/api/investigate", json={})
    assert r.status_code == 422


def test_investigate_streams_sse(client):
    """Full integration: POST /api/investigate yields SSE events in expected order."""
    with client.stream(
        "POST", "/api/investigate", json={"question": "Why did metric X drop?"}
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = _parse_sse(response.iter_lines())

    types = [e.get("data", {}).get("type") for e in events]
    assert "run_started" in types
    assert "phase" in types
    assert "evidence" in types
    assert "report" in types
    assert "done" in types
    assert types[-1] == "done"


def test_investigate_report_has_required_fields(client):
    with client.stream("POST", "/api/investigate", json={"question": "test"}) as response:
        events = _parse_sse(response.iter_lines())

    report_events = [e["data"] for e in events if e.get("data", {}).get("type") == "report"]
    assert len(report_events) == 1
    report = report_events[0]
    assert "user_question" in report
    assert "text" in report
    assert "evidence_count" in report
    assert "critique_passed" in report


def test_investigate_evidence_has_required_fields(client):
    with client.stream("POST", "/api/investigate", json={"question": "test"}) as response:
        events = _parse_sse(response.iter_lines())

    evidence_events = [e["data"] for e in events if e.get("data", {}).get("type") == "evidence"]
    assert len(evidence_events) >= 1
    ev = evidence_events[0]
    assert "index" in ev
    assert "tool_name" in ev
    assert "args" in ev
    assert "output" in ev


def test_investigate_run_started_has_run_id(client):
    with client.stream("POST", "/api/investigate", json={"question": "test"}) as response:
        events = _parse_sse(response.iter_lines())

    started = [e["data"] for e in events if e.get("data", {}).get("type") == "run_started"]
    assert len(started) == 1
    assert "run_id" in started[0]
    assert started[0]["user_question"] == "test"


def test_phase_events_include_known_phases(client):
    with client.stream("POST", "/api/investigate", json={"question": "test"}) as response:
        events = _parse_sse(response.iter_lines())

    phase_events = [e["data"] for e in events if e.get("data", {}).get("type") == "phase"]
    assert len(phase_events) >= 1
    known = {"plan", "decompose", "drill", "cross_check", "critique", "report"}
    for pe in phase_events:
        assert pe["phase"] in known
