from __future__ import annotations

import asyncio
from collections import defaultdict

from app.models import Event


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=512)
        async with self._lock:
            self._subscribers[task_id].add(queue)
        return queue

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue[Event]) -> None:
        async with self._lock:
            self._subscribers[task_id].discard(queue)
            if not self._subscribers[task_id]:
                self._subscribers.pop(task_id, None)

    async def publish(self, event: Event) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(event.task_id, ()))
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A slow browser tab must not stall the agent loop.
                pass
