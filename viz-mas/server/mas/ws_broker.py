"""Per-session WebSocket fan-out for streaming agent dialogues.

Each negotiation gets a topic = `negotiate:{husband_id}`. Publishers
(agent / negotiator) push events; subscribers (frontend V5) receive them.
The broker keeps an in-memory replay buffer so a client connecting
mid-stream catches up.

Verbatim port of the reference at
D:/projects/jiapu-hgt-final/backend/app/services/ws_broker.py.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

log = logging.getLogger(__name__)


class WSBroker:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._replay: dict[str, list[dict]] = defaultdict(list)
        self._closed: dict[str, bool] = {}

    async def subscribe(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._queues[topic].append(q)
            for ev in self._replay.get(topic, []):
                await q.put(ev)
        return q

    async def unsubscribe(self, topic: str, q: asyncio.Queue) -> None:
        async with self._lock:
            if q in self._queues.get(topic, []):
                self._queues[topic].remove(q)

    async def publish(self, topic: str, event: dict) -> None:
        async with self._lock:
            self._replay[topic].append(event)
            for q in list(self._queues.get(topic, [])):
                await q.put(event)

    async def close(self, topic: str) -> None:
        await self.publish(topic, {"type": "done"})
        async with self._lock:
            self._closed[topic] = True

    def is_closed(self, topic: str) -> bool:
        return self._closed.get(topic, False)

    def replay(self, topic: str) -> list[dict]:
        return list(self._replay.get(topic, []))

    def reset(self, topic: str) -> None:
        """Clear replay + closed flag so a re-run of the same topic starts fresh."""
        self._replay.pop(topic, None)
        self._closed.pop(topic, None)


broker = WSBroker()
