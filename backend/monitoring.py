"""
Monitoring channel.

The agent broadcasts structured JSON events over a LiveKit *data channel* so
that any participant in the room (specifically the monitoring dashboard) can
render a live view of what the agent is doing.

We use two topics:
  * "monitor"  -> agent -> watcher   (transcript, state, intent, action, status, summary)
  * "control"  -> watcher -> agent   (takeover / resume commands)

Keeping this in one place means the frontend and backend share exactly one
event vocabulary.  The TypeScript mirror of these shapes lives in
frontend/lib/monitor-events.ts — keep them in sync.
"""
from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Optional

from livekit import rtc

MONITOR_TOPIC = "monitor"
CONTROL_TOPIC = "control"


class AgentState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    HUMAN_CONTROLLED = "human_controlled"


class CallStatus(str, Enum):
    CONNECTED = "connected"
    TRANSFERRING = "transferring"
    ENDED = "ended"


def _now_ms() -> int:
    return int(time.time() * 1000)


class MonitorPublisher:
    """Thin wrapper around room.local_participant.publish_data."""

    def __init__(self, room: rtc.Room):
        self._room = room

    async def _send(self, payload: dict[str, Any]) -> None:
        payload.setdefault("ts", _now_ms())
        try:
            await self._room.local_participant.publish_data(
                json.dumps(payload).encode("utf-8"),
                reliable=True,
                topic=MONITOR_TOPIC,
            )
        except Exception as exc:  # never let monitoring crash the call
            print(f"[monitor] publish failed: {exc}")

    # ---- individual event helpers -------------------------------------
    async def transcript(self, role: str, text: str, final: bool = True) -> None:
        """role: 'caller' | 'agent' | 'watcher'"""
        await self._send(
            {"type": "transcript", "role": role, "text": text, "final": final}
        )

    async def state(self, state: AgentState) -> None:
        await self._send({"type": "state", "state": state.value})

    async def intent(self, intent: str, confidence: Optional[float] = None) -> None:
        await self._send({"type": "intent", "intent": intent, "confidence": confidence})

    async def action(self, action: str, detail: str = "") -> None:
        """e.g. action='checking_availability', detail='2026-07-01 10:00'"""
        await self._send({"type": "action", "action": action, "detail": detail})

    async def status(self, status: CallStatus) -> None:
        await self._send({"type": "status", "status": status.value})

    async def summary(self, summary: str, booking: Optional[dict] = None) -> None:
        await self._send({"type": "summary", "summary": summary, "booking": booking})


def parse_control(data: bytes) -> Optional[dict]:
    """Parse an inbound control message from the watcher.

    Expected: {"command": "takeover" | "resume"}
    """
    try:
        msg = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(msg, dict) and msg.get("command") in ("takeover", "resume"):
        return msg
    return None
