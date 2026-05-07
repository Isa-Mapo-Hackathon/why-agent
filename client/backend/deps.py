"""Cached graph dependency — imported here so tests can patch build_graph."""

from functools import lru_cache

from agent.graph import build_graph  # noqa: F401


@lru_cache(maxsize=1)
def get_graph():
    """Return a cached compiled LangGraph instance (built once per process)."""
    return build_graph()
