"""
LiveKit Agents worker entrypoint.

Run with:
    python agent.py dev        # hot-reload, connects to LiveKit Cloud/dev
    python agent.py start       # production worker

What this file does:
  * Builds the AgentSession (STT/LLM/TTS/VAD/turn-detection from providers.py).
  * Starts Agent A (BookingAgent).
  * Streams monitoring events (state / transcript / status) to the dashboard.
  * Handles watcher take-over / resume on the "control" data channel.
  * Generates a post-call summary when the caller leaves.
"""
from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    AgentSession,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    metrics,
)

import db
import providers
import summary
from booking_agent import BookingAgent
from monitoring import (
    CONTROL_TOPIC,
    AgentState,
    CallStatus,
    MonitorPublisher,
    parse_control,
)

load_dotenv()
logger = logging.getLogger("voice-agent")
logging.basicConfig(level=logging.INFO)


def prewarm(proc: JobProcess) -> None:
    """Load the (CPU-heavy) VAD model once per worker process."""
    proc.userdata["vad"] = providers.build_vad()


async def entrypoint(ctx: JobContext) -> None:
    db.init_db()
    await ctx.connect()

    monitor = MonitorPublisher(ctx.room)
    agent = BookingAgent(monitor)

    # NOTE: turn_detection via the multilingual model runs in a separate
    # inference process that can hang on some Windows setups and stall the
    # connection. We rely on Silero VAD for end-of-turn detection instead,
    # which is reliable and starts instantly. To re-enable the smarter model,
    # add: turn_detection=providers.build_turn_detection()
    session = AgentSession(
        stt=providers.build_stt(),
        llm=providers.build_llm(),
        tts=providers.build_tts(),
        vad=ctx.proc.userdata.get("vad") or providers.build_vad(),
    )

    # ---- monitoring: agent state ------------------------------------
    _STATE_MAP = {
        "listening": AgentState.LISTENING,
        "thinking": AgentState.THINKING,
        "speaking": AgentState.SPEAKING,
        "initializing": AgentState.IDLE,
        "idle": AgentState.IDLE,
    }

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:
        if agent.transferred:
            return  # human is in control; ignore agent state churn
        state = _STATE_MAP.get(getattr(ev, "new_state", ""), AgentState.IDLE)
        asyncio.create_task(monitor.state(state))

    # ---- monitoring: finalized transcript lines ---------------------
    @session.on("conversation_item_added")
    def _on_item(ev) -> None:
        item = getattr(ev, "item", None)
        if item is None:
            return
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", None)
        if not text:
            return
        if role == "assistant":
            asyncio.create_task(monitor.transcript("agent", text, final=True))
        elif role == "user":
            asyncio.create_task(monitor.transcript("caller", text, final=True))

    # ---- monitoring: interim caller transcript ----------------------
    @session.on("user_input_transcribed")
    def _on_user_transcript(ev) -> None:
        if getattr(ev, "is_final", False):
            return  # finals come through conversation_item_added
        text = getattr(ev, "transcript", "")
        if text:
            asyncio.create_task(monitor.transcript("caller", text, final=False))

    # ---- metrics logging (optional, handy in dev) -------------------
    usage = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:
        metrics.log_metrics(ev.metrics)
        usage.collect(ev.metrics)

    # ---- watcher take-over / resume ---------------------------------
    async def _set_paused(paused: bool) -> None:
        try:
            session.input.set_audio_enabled(not paused)
        except Exception as exc:
            logger.warning("could not toggle session audio input: %s", exc)
        if paused:
            session.interrupt()  # stop any in-flight speech immediately
            await monitor.state(AgentState.HUMAN_CONTROLLED)
            logger.info("agent paused — watcher has taken over")
        else:
            await monitor.state(AgentState.LISTENING)
            logger.info("agent resumed")

    @ctx.room.on("data_received")
    def _on_data(packet: rtc.DataPacket) -> None:
        if packet.topic != CONTROL_TOPIC:
            return
        msg = parse_control(packet.data)
        if not msg:
            return
        asyncio.create_task(_set_paused(msg["command"] == "takeover"))

    # ---- end-of-call summary ----------------------------------------
    _ended = asyncio.Event()

    async def _end_call() -> None:
        if _ended.is_set():
            return
        _ended.set()
        await monitor.status(CallStatus.ENDED)
        try:
            text = await summary.post_call_summary(
                session.history.items, agent.last_booking
            )
        except Exception as exc:
            logger.warning("summary generation failed: %s", exc)
            text = "Summary unavailable."
        db.save_summary(ctx.room.name, text, agent.last_booking)
        # Publish live too (the dashboard is usually still connected here).
        await monitor.summary(text, agent.last_booking)
        logger.info("post-call summary:\n%s", text)

    @ctx.room.on("participant_disconnected")
    def _on_left(participant: rtc.RemoteParticipant) -> None:
        # The caller leaving ends the call. Ignore the watcher/monitor leaving.
        if participant.identity.startswith("monitor"):
            return
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            return
        asyncio.create_task(_end_call())

    ctx.add_shutdown_callback(_end_call)

    # ---- go ----------------------------------------------------------
    await session.start(agent=agent, room=ctx.room)
    await monitor.status(CallStatus.CONNECTED)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm)
    )
