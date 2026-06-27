"""
Agent A — the conversational booking agent.

Responsibilities:
  * Hold a natural conversation.
  * Book appointments via tool calls (check availability -> confirm -> book).
  * Detect when the caller needs a human and kick off a warm transfer.

Every tool call also emits monitoring events (intent / action) so the live
dashboard reflects exactly what the agent is doing.
"""
from __future__ import annotations

import asyncio
import datetime as dt

from livekit.agents import Agent, RunContext, function_tool, get_job_context

import db
from monitoring import AgentState, CallStatus, MonitorPublisher
from warm_transfer import WarmTransfer

INSTRUCTIONS = """\
You are Riley, a warm and efficient voice receptionist for "Northside Health
Clinic". You are speaking on a phone call, so keep replies short and natural —
one or two sentences, no lists, no markdown.

You can do two things:
1. Book an appointment. Collect ALL of: full name, reason for visit, preferred
   date, preferred time, and a contact phone number. Ask for missing pieces one
   at a time. Before confirming, call `check_availability`. Only after the slot
   is confirmed free, read the details back and call `book_appointment`. Then
   confirm the booking out loud.
2. Connect the caller to a human when they ask for a person, or for anything
   you can't handle — billing, complaints, insurance disputes, "talk to
   someone". In that case call `request_human` with a short reason.

Today's date is {today}. Interpret relative dates ("tomorrow", "next Monday")
into concrete calendar dates before calling tools. Never invent availability —
always use the tool. If a time is taken, offer the alternatives the tool
returns.
"""


class BookingAgent(Agent):
    def __init__(self, monitor: MonitorPublisher) -> None:
        super().__init__(
            instructions=INSTRUCTIONS.format(
                today=dt.date.today().isoformat()
            )
        )
        self.monitor = monitor
        self.last_booking: dict | None = None
        self.transferred = False

    async def on_enter(self) -> None:
        await self.monitor.state(AgentState.SPEAKING)
        await self.session.generate_reply(
            instructions=(
                "Greet the caller: introduce yourself as Riley at Northside "
                "Health Clinic and ask how you can help."
            )
        )

    # ---- Tool: availability check ------------------------------------
    @function_tool()
    async def check_availability(self, ctx: RunContext, date: str, time: str):
        """Check whether an appointment slot is free.

        Args:
            date: ISO calendar date, e.g. "2026-07-01".
            time: 24-hour time in "HH:MM", on the hour or half hour.
        """
        await self.monitor.intent("booking")
        await self.monitor.action("checking_availability", f"{date} {time}")

        available = await asyncio.to_thread(db.is_available, date, time)
        if available:
            return {"available": True, "date": date, "time": time}

        alternatives = await asyncio.to_thread(db.suggest_alternatives, date, time)
        return {
            "available": False,
            "date": date,
            "time": time,
            "alternatives": alternatives,
        }

    # ---- Tool: booking ------------------------------------------------
    @function_tool()
    async def book_appointment(
        self,
        ctx: RunContext,
        name: str,
        reason: str,
        date: str,
        time: str,
        phone: str,
    ):
        """Book a confirmed appointment. Only call after check_availability
        returned available=True and you've read the details back.

        Args:
            name: caller's full name.
            reason: reason for the visit.
            date: ISO date "YYYY-MM-DD".
            time: 24-hour "HH:MM".
            phone: contact number in any readable format.
        """
        await self.monitor.action("booking", f"{name} · {date} {time}")

        appt = await asyncio.to_thread(db.book, name, reason, date, time, phone)
        if appt is None:
            alternatives = await asyncio.to_thread(db.suggest_alternatives, date, time)
            return {"booked": False, "reason": "slot_taken", "alternatives": alternatives}

        self.last_booking = db.to_dict(appt)
        await self.monitor.action("booked", f"{date} {time}")
        return {"booked": True, "appointment": self.last_booking}

    # ---- Tool: human handoff (warm transfer) --------------------------
    @function_tool()
    async def request_human(self, ctx: RunContext, reason: str):
        """Warm-transfer the caller to a human agent.

        Args:
            reason: short reason the caller needs a person (e.g. "billing
                dispute", "wants to speak to a person").
        """
        await self.monitor.intent("human_handoff")
        await self.monitor.action("transferring", reason)
        await self.monitor.status(CallStatus.TRANSFERRING)

        # Tell the caller we're connecting them before we dial out.
        await ctx.session.generate_reply(
            instructions=(
                "Tell the caller, warmly: you'll connect them to a team member "
                "now and to please hold for a moment."
            )
        )

        job_ctx = get_job_context()
        transfer = WarmTransfer(job_ctx.room)
        try:
            accepted = await transfer.run(self.session.history.items, reason)
        except Exception as exc:
            await self.monitor.action("transfer_failed", str(exc))
            await self.monitor.status(CallStatus.CONNECTED)
            return {
                "transferred": False,
                "reason": "error",
                "say": "I'm sorry, I couldn't reach the team right now.",
            }

        if accepted:
            self.transferred = True
            await self.monitor.state(AgentState.HUMAN_CONTROLLED)
            # Say goodbye to the caller, let it play, then Agent A bows out.
            # The human was already moved into this room by WarmTransfer, so
            # caller + human keep talking after the agent shuts down.
            await ctx.session.generate_reply(
                instructions="Say warmly: 'You're connected now, take care!'"
            )
            # Give the shutdown hook a beat to run the post-call summary, then
            # disconnect the agent worker from the room.
            asyncio.create_task(_shutdown_soon(job_ctx))
            return {"transferred": True}

        # Declined / no-answer: return to the caller.
        await self.monitor.status(CallStatus.CONNECTED)
        await self.monitor.intent("general")
        return {
            "transferred": False,
            "reason": "unavailable",
            "say": (
                "Tell the caller, apologetically, that the team isn't available "
                "right now, and ask if there's anything else you can help with "
                "or if they'd like to leave a message."
            ),
        }


async def _shutdown_soon(job_ctx, delay: float = 4.0) -> None:
    """Let the goodbye line finish, then end the agent's job so it leaves the
    room. The room (caller + human) stays alive until they hang up."""
    await asyncio.sleep(delay)
    try:
        job_ctx.shutdown(reason="warm_transfer_complete")
    except Exception:
        pass
