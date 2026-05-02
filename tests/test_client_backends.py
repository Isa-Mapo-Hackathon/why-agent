"""Verifies the MODEL_BACKEND switch in agent.client.

These are construction-only smoke tests. No network. No invocation. They
exist because the multi-backend client is critical infrastructure: if it
silently routes to the wrong backend, every downstream module is wrong.
"""

import json

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from agent.client import ReplayClient, get_llm
from agent.constants import (
    BACKEND_MINIMAX,
    BACKEND_REPLAY,
    BACKEND_VLLM,
    ENV_MINIMAX_API_KEY,
    ENV_MODEL_BACKEND,
    ENV_SCENARIO_ID,
    ENV_VLLM_ENDPOINT,
    MINIMAX_BASE_URL,
    MINIMAX_MODEL,
    VLLM_MODEL,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip backend env vars so tests don't leak host config."""
    for var in (
        ENV_MODEL_BACKEND,
        ENV_MINIMAX_API_KEY,
        ENV_VLLM_ENDPOINT,
        ENV_SCENARIO_ID,
    ):
        monkeypatch.delenv(var, raising=False)


def test_minimax_backend_returns_chat_openai(monkeypatch):
    monkeypatch.setenv(ENV_MODEL_BACKEND, BACKEND_MINIMAX)
    monkeypatch.setenv(ENV_MINIMAX_API_KEY, "test-key")

    client = get_llm()

    assert isinstance(client, ChatOpenAI)
    assert client.model_name == MINIMAX_MODEL
    assert str(client.openai_api_base) == MINIMAX_BASE_URL


def test_vllm_backend_returns_chat_openai(monkeypatch):
    monkeypatch.setenv(ENV_MODEL_BACKEND, BACKEND_VLLM)
    monkeypatch.setenv(ENV_VLLM_ENDPOINT, "http://localhost:8000/v1")

    client = get_llm()

    assert isinstance(client, ChatOpenAI)
    assert client.model_name == VLLM_MODEL
    assert str(client.openai_api_base) == "http://localhost:8000/v1"


def test_replay_backend_returns_replay_client(monkeypatch):
    monkeypatch.setenv(ENV_MODEL_BACKEND, BACKEND_REPLAY)

    client = get_llm(scenario_id="demo_scenario")

    assert isinstance(client, ReplayClient)


def test_replay_backend_reads_scenario_id_from_env(monkeypatch):
    monkeypatch.setenv(ENV_MODEL_BACKEND, BACKEND_REPLAY)
    monkeypatch.setenv(ENV_SCENARIO_ID, "demo_scenario")

    client = get_llm()

    assert isinstance(client, ReplayClient)


def test_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv(ENV_MODEL_BACKEND, "bogus")

    with pytest.raises(ValueError, match="MODEL_BACKEND"):
        get_llm()


def test_missing_backend_env_var_raises(monkeypatch):
    # ENV_MODEL_BACKEND already removed by autouse fixture.
    with pytest.raises(ValueError, match="MODEL_BACKEND"):
        get_llm()


def test_minimax_missing_api_key_raises(monkeypatch):
    monkeypatch.setenv(ENV_MODEL_BACKEND, BACKEND_MINIMAX)

    with pytest.raises(ValueError, match=ENV_MINIMAX_API_KEY):
        get_llm()


def test_vllm_missing_endpoint_raises(monkeypatch):
    monkeypatch.setenv(ENV_MODEL_BACKEND, BACKEND_VLLM)

    with pytest.raises(ValueError, match=ENV_VLLM_ENDPOINT):
        get_llm()


def test_replay_missing_scenario_id_raises(monkeypatch):
    monkeypatch.setenv(ENV_MODEL_BACKEND, BACKEND_REPLAY)

    with pytest.raises(ValueError, match="scenario"):
        get_llm()


def test_replay_bind_tools_is_noop():
    """LangGraph's create_react_agent calls .bind_tools() on the model.
    Replay encodes tool calls in the JSON, so bind_tools must return self
    rather than raising NotImplementedError from BaseChatModel.
    """
    client = ReplayClient(scenario_id="anything")

    bound = client.bind_tools([{"name": "fake_tool"}])

    assert bound is client


def test_replay_advances_through_recorded_turns(tmp_path):
    scenario = "two_turn"
    (tmp_path / f"{scenario}.json").write_text(
        json.dumps(
            [
                {"content": "first response", "tool_calls": []},
                {"content": "second response", "tool_calls": []},
            ]
        )
    )
    client = ReplayClient(scenario_id=scenario, replays_dir=tmp_path)

    first = client.invoke([HumanMessage(content="hi")])
    second = client.invoke([HumanMessage(content="again")])

    assert first.content == "first response"
    assert second.content == "second response"


def test_replay_raises_when_exhausted(tmp_path):
    scenario = "one_turn"
    (tmp_path / f"{scenario}.json").write_text(
        json.dumps([{"content": "only response", "tool_calls": []}])
    )
    client = ReplayClient(scenario_id=scenario, replays_dir=tmp_path)

    client.invoke([HumanMessage(content="hi")])

    with pytest.raises(IndexError, match="exhausted"):
        client.invoke([HumanMessage(content="again")])
