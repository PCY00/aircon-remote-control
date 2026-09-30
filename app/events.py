"""Small in-process event stream for live dashboard updates."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from threading import Lock


class EventHub:
    """Broadcast JSON-safe events from MQTT threads to async SSE clients."""

    def __init__(self, *, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()
        self._sequence = 0
        self._lock = Lock()

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()

    async def stop(self) -> None:
        self._subscribers.clear()
        self._loop = None

    def publish(self, event_type: str, data: dict[str, object]) -> dict[str, object]:
        with self._lock:
            self._sequence += 1
            event = {
                "id": self._sequence,
                "type": event_type,
                "occurred_at": datetime.now(UTC).isoformat(),
                "data": data,
            }
            loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._deliver, event)
        return event

    def _deliver(self, event: dict[str, object]) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, object]]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(
            maxsize=self._queue_size
        )
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


def format_sse(event: dict[str, object]) -> str:
    """Serialize one event using the Server-Sent Events wire format."""

    event_id = event.get("id")
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"{prefix}data: {payload}\n\n"
