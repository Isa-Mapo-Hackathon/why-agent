"""SSE event formatting for sse-starlette EventSourceResponse."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any


class _Encoder(json.JSONEncoder):
    """Extends the default encoder to handle date/datetime objects in tool args."""

    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


def to_sse(event_type: str, data: dict[str, Any]) -> dict[str, str]:
    """Return a dict that sse-starlette will send as a single SSE event.

    The frontend reads event.data and JSON.parses it; `type` is included in the
    payload so the client can dispatch without needing the SSE `event:` field.
    """
    return {"event": event_type, "data": json.dumps({**data, "type": event_type}, cls=_Encoder)}
