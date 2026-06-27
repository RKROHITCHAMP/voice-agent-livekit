"""
Warm (agent-assisted) transfer over Twilio SIP.

Flow implemented here (the classic "consultation" pattern):

  1. Agent A decides the caller needs a human.
  2. We generate a short spoken briefing from the conversation so far.
  3. We spin up a private *transfer room* and dial the human agent's phone
     through the LiveKit -> Twilio SIP outbound trunk.
  4. A lightweight consultation session (TransferAgent) greets the human,
     reads the briefing, and asks whether they want to take the call.
        - The human can answer by voice ("yes, put them through" / "no") or
          by DTMF (press 1 to accept, 2 to decline).
  5a. ACCEPT  -> we MoveParticipant the human into the caller's room, Agent A
                 says goodbye and disconnects, leaving caller + human talking.
  5b. DECLINE -> we tear the transfer room down, Agent A returns to the caller
                 and explains the team isn't available right now.

Everything that touches live telephony is isolated in this module so the rest
of the app has no SIP knowledge.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

from livekit import api, rtc
from livekit.agents import Agent, AgentSession, RunContext, function_tool

import providers
import summary

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")


class _Decision:
    """Shared result object set by the TransferAgent's tools."""

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.accepted: Optional[bool] = None
        self.reason: str = ""

    def resolve(self, accepted: bool, reason: str = "") -> None:
        if not self.event.is_set():
            self.accepted = accepted
            self.reason = reason
            self.event.set()


class TransferAgent(Agent):
    """The agent that talks privately to the human before handover."""

    def __init__(self, briefing: str, decision: _Decision) -> None:
        super().__init__(
            instructions=(
                "You are an automated assistant briefing a human support agent "
                "who just picked up the phone. Greet them briefly, read the "
                "briefing, then clearly ask: 'Would you like to take this call? "
                "Say yes, or press 1 to accept and 2 to decline.' "
                "When they accept, call accept_transfer. When they decline, call "
                "decline_transfer. Do not chat about anything else."
                f"\n\nBriefing to read:\n{briefing}"
            )
        )
        self._decision = decision

    async def on_enter(self) -> None:
        # Speak the greeting + briefing as soon as the human connects.
        await self.session.generate_reply()

    @function_tool()
    async def accept_transfer(self, ctx: RunContext):
        """Call this when the human agent agrees to take the call."""
        await ctx.session.generate_reply(
            instructions="Say: 'Great, connecting you now.'"
        )
        self._decision.resolve(True)
        return "accepted"

    @function_tool()
    async def decline_transfer(self, ctx: RunContext, reason: str = "unavailable"):
        """Call this when the human agent does NOT want to take the call.

        Args:
            reason: short explanation, e.g. 'busy', 'unavailable'.
        """
        await ctx.session.generate_reply(
            instructions="Say: 'No problem, thanks.' then stop."
        )
        self._decision.resolve(False, reason)
        return "declined"


class WarmTransfer:
    def __init__(self, caller_room: rtc.Room):
        self.caller_room = caller_room
        self.caller_room_name = caller_room.name
        self.transfer_room_name = f"{caller_room.name}-transfer-{uuid.uuid4().hex[:6]}"
        self._consult_room: Optional[rtc.Room] = None
        self._consult_session: Optional[AgentSession] = None

    def _human_token(self) -> str:
        return (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity("transfer-agent")
            .with_name("Transfer Agent")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=self.transfer_room_name,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
            .to_jwt()
        )

    async def run(self, history_items, reason: str) -> bool:
        """Execute the warm transfer.  Returns True if the human accepted
        (caller has been connected to them), False otherwise."""
        trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
        human_number = os.getenv("HUMAN_AGENT_NUMBER")
        if not trunk_id or not human_number:
            raise RuntimeError(
                "SIP_OUTBOUND_TRUNK_ID and HUMAN_AGENT_NUMBER must be set for transfer"
            )

        briefing = await summary.spoken_briefing(history_items, reason)
        decision = _Decision()

        async with api.LiveKitAPI(
            LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
        ) as lkapi:
            # 1. Dial the human into the private transfer room.
            await lkapi.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    sip_trunk_id=trunk_id,
                    sip_call_to=human_number,
                    room_name=self.transfer_room_name,
                    participant_identity="human-agent",
                    participant_name="Human Agent",
                    # wait for the human to actually pick up before we talk
                    wait_until_answered=True,
                )
            )

            # 2. Join the transfer room and run the consultation session.
            self._consult_room = rtc.Room()
            await self._consult_room.connect(LIVEKIT_URL, self._human_token())

            self._consult_session = AgentSession(
                stt=providers.build_stt(),
                llm=providers.build_llm(),
                tts=providers.build_tts(),
                vad=providers.build_vad(),
            )
            # DTMF fallback: 1 = accept, 2 = decline.
            self._consult_room.on("sip_dtmf_received", _make_dtmf_handler(decision))

            await self._consult_session.start(
                agent=TransferAgent(briefing, decision),
                room=self._consult_room,
            )

            # 3. Wait for the human's decision (with a safety timeout).
            try:
                await asyncio.wait_for(decision.event.wait(), timeout=60)
            except asyncio.TimeoutError:
                decision.resolve(False, "no answer")

            try:
                if decision.accepted:
                    # 4a. Move the human into the caller's room, then leave.
                    await lkapi.room.move_participant(
                        api.MoveParticipantRequest(
                            room=self.transfer_room_name,
                            identity="human-agent",
                            destination_room=self.caller_room_name,
                        )
                    )
                    return True
                else:
                    # 4b. Hang up the human leg.
                    await lkapi.room.delete_room(
                        api.DeleteRoomRequest(room=self.transfer_room_name)
                    )
                    return False
            finally:
                await self._cleanup()

    async def _cleanup(self) -> None:
        if self._consult_session is not None:
            try:
                await self._consult_session.aclose()
            except Exception:
                pass
        if self._consult_room is not None:
            try:
                await self._consult_room.disconnect()
            except Exception:
                pass


def _make_dtmf_handler(decision: _Decision):
    def _on_dtmf(ev) -> None:
        digit = getattr(ev, "digit", None) or getattr(ev, "code", None)
        if str(digit) == "1":
            decision.resolve(True)
        elif str(digit) == "2":
            decision.resolve(False, "declined via keypad")
    return _on_dtmf
