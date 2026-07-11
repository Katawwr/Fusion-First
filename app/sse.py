"""Server-Sent Events helpers. Keep the wire format identical to what the frontend reader parses."""

from __future__ import annotations

import json


def sse_frame(event: str, data: dict) -> str:
    """One SSE message: an `event:` line plus a single-line JSON `data:` payload."""
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n"


def sse_comment(text: str = "keepalive") -> str:
    """A heartbeat comment — keeps proxies/CDNs from idling out a slow stream."""
    return f": {text}\n\n"
