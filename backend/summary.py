"""
Call summarisation.

Used in two places:
  1. Warm transfer  -> a short spoken briefing for the human agent.
  2. Post-call      -> a structured written summary shown in the dashboard.

Both are produced from the LiveKit chat history (the running transcript the
AgentSession keeps) using the same LLM configured for the conversation.
"""
from __future__ import annotations

import os
from typing import Optional

from openai import AsyncOpenAI

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def _transcript_to_text(items) -> str:
    """Flatten LiveKit ChatContext items into 'Role: text' lines.

    `items` is the list returned by `session.history.items` (v1.x). Each item
    has a `.role` and `.text_content` (str | None). We defensively handle both
    the object form and plain dicts so this keeps working across minor SDK
    bumps.
    """
    lines: list[str] = []
    for it in items:
        role = getattr(it, "role", None) or (it.get("role") if isinstance(it, dict) else None)
        text = getattr(it, "text_content", None)
        if text is None and isinstance(it, dict):
            text = it.get("content")
        if not role or not text:
            continue
        if role == "system":
            continue
        speaker = {"assistant": "Agent", "user": "Caller"}.get(role, role.title())
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


async def spoken_briefing(history_items, reason: str) -> str:
    """A 2-3 sentence briefing the agent reads aloud to the human agent
    before handing over the call."""
    transcript = _transcript_to_text(history_items)
    resp = await _get_client().chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "You brief a human support agent who is about to take over a "
                    "live phone call. In 2-3 short spoken sentences, state who the "
                    "caller is, what they need, and any detail already collected. "
                    "Be concise and natural — this will be read aloud."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Reason the caller needs a human: {reason}\n\n"
                    f"Conversation so far:\n{transcript}"
                ),
            },
        ],
    )
    return resp.choices[0].message.content.strip()


async def post_call_summary(history_items, booking: Optional[dict] = None) -> str:
    """A structured written summary generated when the call ends."""
    transcript = _transcript_to_text(history_items)
    booking_note = ""
    if booking:
        booking_note = (
            f"\n\nA booking was confirmed: {booking.get('name')} on "
            f"{booking.get('date')} at {booking.get('time')} "
            f"for '{booking.get('reason')}' (callback {booking.get('phone')})."
        )
    resp = await _get_client().chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "Summarise the completed phone call for an internal CRM. "
                    "Use these labelled sections, each one line where possible:\n"
                    "Caller intent:\nKey details collected:\nOutcome:\n"
                    "Follow-up needed:\nSentiment:"
                ),
            },
            {
                "role": "user",
                "content": f"Transcript:\n{transcript}{booking_note}",
            },
        ],
    )
    return resp.choices[0].message.content.strip()
