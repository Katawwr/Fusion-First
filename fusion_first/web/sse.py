"""Server-Sent Events helpers. Keep the wire format identical to what the frontend reader parses."""

from __future__ import annotations

import json


def sse_frame(event: str, data: dict) -> str:
    """One SSE message: an `event:` line plus a single-line JSON `data:` payload."""
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n"


def sse_comment(text: str = "keepalive") -> str:
    """A heartbeat comment: keeps proxies/CDNs from idling out a slow stream."""
    return f": {text}\n\n"


def sse_error(code: str, message: str, scan_id: str | None = None) -> str:
    """The terminal error frame. `message` must be user-safe (never a traceback or a secret)."""
    payload = {"type": "error", "code": code, "message": message}
    if scan_id:
        payload["scan_id"] = scan_id
    return sse_frame("error", payload)


async def stream_with_heartbeat(frames, heartbeat_s: float = 15.0):
    """Relay `frames`, emitting a keepalive comment whenever nothing arrived for `heartbeat_s`.

    On client disconnect the producer task is cancelled so the scan stops making model calls."""
    import asyncio

    queue: asyncio.Queue = asyncio.Queue()
    done = object()

    async def produce():
        try:
            async for frame in frames:
                await queue.put(frame)
        except BaseException as exc:  # noqa: BLE001 (re-raised by the consumer)
            await queue.put(exc)
        finally:
            await queue.put(done)

    task = asyncio.create_task(produce())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), heartbeat_s)
            except TimeoutError:
                yield sse_comment()
                continue
            if item is done:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        task.cancel()
        try:
            await task
        except BaseException:  # noqa: BLE001 (cancellation cleanup)
            pass
