"""FastAPI backend — streams investigation progress as Server-Sent Events."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agent.constants import DEMO_QUESTIONS
from agent.state import InvestigationState
from client.backend.deps import get_graph
from client.backend.sse import to_sse

logger = logging.getLogger(__name__)

app = FastAPI(title="why-agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class InvestigateRequest(BaseModel):
    question: str = Field(min_length=1, description="The question to investigate.")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/demo-questions")
def demo_questions() -> dict[str, list[str]]:
    return {"questions": DEMO_QUESTIONS}


@app.post("/api/investigate")
async def investigate(req: InvestigateRequest) -> EventSourceResponse:
    """Stream a root-cause investigation as Server-Sent Events.

    The client POSTs a question and reads the response body as a stream.
    Events are emitted in order: run_started → phase → evidence → report → done.
    """
    run_id = uuid.uuid4().hex
    graph = get_graph()
    init = InvestigationState(user_question=req.question)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue(maxsize=256)
    stop = threading.Event()

    def drive() -> None:
        """Run the sync LangGraph stream in a thread, pushing SSE events into the queue."""
        seen_evidence = 0
        last_phase: str | None = None

        def _push(evt: dict[str, str] | None) -> None:
            # Wrap put_nowait in a closure so QueueFull is caught on the event loop thread
            def _put() -> None:
                try:
                    queue.put_nowait(evt)
                except asyncio.QueueFull:
                    pass  # client too slow or disconnected — drop event

            loop.call_soon_threadsafe(_put)

        try:
            for chunk in graph.stream(init, stream_mode="values"):
                if stop.is_set():
                    return  # client disconnected — bail early

                phase = str(chunk.get("phase", "")).split(".")[-1].lower()
                if phase and phase != last_phase:
                    _push(
                        to_sse(
                            "phase", {"phase": phase, "retry_count": chunk.get("retry_count", 0)}
                        )
                    )
                    last_phase = phase

                evidence: list[Any] = chunk.get("evidence") or []
                for i, e in enumerate(evidence[seen_evidence:], start=seen_evidence):
                    d: dict[str, Any] = e.model_dump() if hasattr(e, "model_dump") else dict(e)
                    d.get("args", {}).pop("_tool_call_id", None)
                    _push(to_sse("evidence", {"index": i, **d}))
                seen_evidence = len(evidence)

                if chunk.get("final_report"):
                    _push(to_sse("report", chunk["final_report"]))

        except Exception as exc:
            logger.exception("Graph stream failed for run %s", run_id)
            _push(to_sse("error", {"message": str(exc)}))
        finally:
            _push(None)  # sentinel — signals gen() to send done and exit

    async def gen():
        yield to_sse("run_started", {"run_id": run_id, "user_question": req.question})
        fut = loop.run_in_executor(None, drive)
        fut.add_done_callback(
            lambda f: logger.error("drive() raised: %s", f.exception()) if f.exception() else None
        )
        try:
            while True:
                evt = await queue.get()
                if evt is None:
                    yield to_sse("done", {})
                    return
                yield evt
        except asyncio.CancelledError:
            raise
        finally:
            stop.set()  # signal the thread to exit on the next iteration

    return EventSourceResponse(gen())
