"""LLM client factory.

Critical infrastructure: every other module in this codebase imports
``get_llm`` from here and never instantiates an LLM directly. The
``MODEL_BACKEND`` env var picks one of three backends:

* ``minimax`` — ChatOpenAI-compatible client at the MiniMax API.
* ``vllm``    — ChatOpenAI-compatible client at a local vLLM endpoint.
* ``replay``  — Reads pre-recorded JSON from ``replays/<scenario_id>.json``.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import Field

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
    VALID_BACKENDS,
    VLLM_MODEL,
)

logger = logging.getLogger(__name__)

REPLAYS_DIR = Path(__file__).resolve().parent.parent / "replays"


def get_llm(scenario_id: str | None = None) -> BaseChatModel:
    """Build an LLM client based on the ``MODEL_BACKEND`` env var.

    Args:
        scenario_id: Required when ``MODEL_BACKEND=replay``. Names the
            JSON file under ``replays/`` to play back. May also come
            from the ``REPLAY_SCENARIO_ID`` env var.

    Returns:
        A ``BaseChatModel`` instance suitable for use by LangGraph.

    Raises:
        ValueError: If ``MODEL_BACKEND`` is unset, unknown, or the
            backend's required env vars are missing.
    """
    backend = os.getenv(ENV_MODEL_BACKEND, "").strip().lower()

    if not backend:
        raise ValueError(
            f"{ENV_MODEL_BACKEND} is not set. Expected one of: {sorted(VALID_BACKENDS)}."
        )
    if backend not in VALID_BACKENDS:
        raise ValueError(
            f"{ENV_MODEL_BACKEND}={backend!r} is not recognized. "
            f"Expected one of: {sorted(VALID_BACKENDS)}."
        )

    if backend == BACKEND_MINIMAX:
        return _build_minimax()
    if backend == BACKEND_VLLM:
        return _build_vllm()
    return _build_replay(scenario_id)


def _build_minimax() -> ChatOpenAI:
    api_key = os.getenv(ENV_MINIMAX_API_KEY)
    if not api_key:
        raise ValueError(
            f"{ENV_MINIMAX_API_KEY} is required when {ENV_MODEL_BACKEND}={BACKEND_MINIMAX}."
        )
    return ChatOpenAI(
        model=MINIMAX_MODEL,
        api_key=api_key,
        base_url=MINIMAX_BASE_URL,
    )


def _build_vllm() -> ChatOpenAI:
    endpoint = os.getenv(ENV_VLLM_ENDPOINT)
    if not endpoint:
        raise ValueError(
            f"{ENV_VLLM_ENDPOINT} is required when {ENV_MODEL_BACKEND}={BACKEND_VLLM}."
        )
    return ChatOpenAI(
        model=VLLM_MODEL,
        api_key="not-needed",
        base_url=endpoint,
    )


def _build_replay(scenario_id: str | None) -> ReplayClient:
    sid = scenario_id or os.getenv(ENV_SCENARIO_ID)
    if not sid:
        raise ValueError(
            "A scenario_id is required when "
            f"{ENV_MODEL_BACKEND}={BACKEND_REPLAY}. "
            f"Pass it via get_llm(scenario_id=...) or set {ENV_SCENARIO_ID}."
        )
    return ReplayClient(scenario_id=sid)


class ReplayClient(BaseChatModel):
    """Plays back a recorded LLM session — no network calls.

    Reads ``replays/<scenario_id>.json`` and yields the ``AIMessage`` /
    tool-call sequence that the live agent produced when recorded. Used
    by the public demo when the GPU is off.

    File format (one record per turn):
        [{"content": "...", "tool_calls": [...]}, ...]
    """

    scenario_id: str = Field(..., description="Replay file stem under replays/.")
    replays_dir: Path = Field(default_factory=lambda: REPLAYS_DIR)
    _turns: list[dict[str, Any]] | None = None
    _index: int = 0

    @property
    def _llm_type(self) -> str:
        return "replay"

    def bind_tools(
        self,
        tools: list[BaseTool | dict[str, Any] | type] | None = None,
        **kwargs: Any,
    ) -> Runnable:
        """No-op: tool-call sequences are already encoded in the replay file."""
        return self

    def _load(self) -> list[dict[str, Any]]:
        if self._turns is not None:
            return self._turns
        path = self.replays_dir / f"{self.scenario_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Replay file not found: {path}")
        self._turns = json.loads(path.read_text())
        return self._turns

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        turns = self._load()
        if self._index >= len(turns):
            raise IndexError(f"Replay {self.scenario_id!r} exhausted after {len(turns)} turns.")
        turn = turns[self._index]
        self._index += 1
        msg = AIMessage(
            content=turn.get("content", ""),
            tool_calls=turn.get("tool_calls", []),
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])
