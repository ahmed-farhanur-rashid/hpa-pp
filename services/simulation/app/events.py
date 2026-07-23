"""WebSocket event broadcaster for real-time simulation streaming.

Provides a fan-out pub/sub mechanism so that the tick loop can push
metrics, cluster state, and lifecycle events to all connected WebSocket
clients without blocking the simulation.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


# ── Channel constants ───────────────────────────────────────────

CHANNEL_METRICS = "metrics"
CHANNEL_CLUSTER = "cluster"
CHANNEL_STATUS = "status"

ALL_CHANNELS = {CHANNEL_METRICS, CHANNEL_CLUSTER, CHANNEL_STATUS}


# ── Event envelope ──────────────────────────────────────────────


def make_event(channel: str, event: str, data: Any, **extra: Any) -> str:
    """Build a JSON event envelope for WebSocket broadcast.

    Args:
        channel: Target channel (metrics / cluster / status).
        event: Event type, e.g. ``"tick"``, ``"snapshot"``, ``"started"``.
        data: Serialisable payload for the event.
        **extra: Extra fields merged at the top level (e.g. tick_count).

    Returns:
        A JSON-encoded string ready for ``send_text``.
    """
    payload: dict[str, Any] = {
        "channel": channel,
        "event": event,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data": data,
    }
    payload.update(extra)
    return json.dumps(payload, default=str)


# ── Broadcaster ─────────────────────────────────────────────────


class EventBroadcaster:
    """Fan-out event broadcaster backed by per-channel subscriber sets.

    Usage::

        broadcaster = EventBroadcaster()
        await broadcaster.subscribe("metrics", websocket)
        ...
        # Broadcast fires the event to every subscriber; dead connections
        # are pruned automatically during each broadcast.
        await broadcaster.broadcast_event("metrics", "tick", {"msg": "hi"})
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[WebSocket]] = {
            ch: set() for ch in ALL_CHANNELS
        }

    # ── Subscription management ─────────────────────────────────

    async def subscribe(self, channel: str, ws: WebSocket) -> None:
        """Register *ws* for events on *channel*."""
        async with self._lock:
            self._subscribers.setdefault(channel, set()).add(ws)

    async def unsubscribe(self, channel: str, ws: WebSocket) -> None:
        """Remove *ws* from *channel*."""
        async with self._lock:
            self._subscribers.get(channel, set()).discard(ws)

    # ── Broadcasting ────────────────────────────────────────────

    async def broadcast(self, channel: str, message: str) -> None:
        """Send a pre-serialised *message* to all subscribers on *channel*.

        Dead connections are detected and pruned automatically.
        """
        subs = self._subscribers.get(channel, set())
        if not subs:
            return

        # Snapshot subscribers under the lock so we can send outside it.
        async with self._lock:
            targets: set[WebSocket] = set(subs)

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._subscribers[channel].discard(ws)

    async def broadcast_event(
        self,
        channel: str,
        event: str,
        data: Any,
        **extra: Any,
    ) -> None:
        """Convenience: build an event envelope and broadcast it in one call."""
        message = make_event(channel, event, data, **extra)
        await self.broadcast(channel, message)
