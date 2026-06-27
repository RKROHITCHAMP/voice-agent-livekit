"""
Central place that wires up the AI providers so both the main booking
session and the warm-transfer consultation session use identical config.

Stack (all have free tiers, all first-class in LiveKit Agents):
  * LLM : Groq             (default, free, no credit card) — OpenAI optional
  * STT : Deepgram nova-3
  * TTS : Deepgram Aura-2
  * VAD : Silero            (local, free, no API key)
  * Turn detection : LiveKit multilingual turn detector (local)

Swap any of these by editing this one file — nothing else references the
provider classes directly. Set LLM_PROVIDER=openai (with OPENAI_API_KEY) to
use OpenAI instead of Groq.
"""
from __future__ import annotations

import os

from livekit.plugins import deepgram, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel


def build_llm() -> openai.LLM:
    # Default: Groq (free, no card). Groq is OpenAI-API-compatible, so the
    # LiveKit OpenAI plugin talks to it via `.with_groq()` (reads GROQ_API_KEY).
    if os.getenv("LLM_PROVIDER", "groq").lower() == "openai":
        return openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4o-mini"))
    return openai.LLM.with_groq(
        model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    )


def build_stt() -> deepgram.STT:
    return deepgram.STT(model=os.getenv("STT_MODEL", "nova-3"), language="multi")


def build_tts() -> deepgram.TTS:
    return deepgram.TTS(model=os.getenv("TTS_VOICE", "aura-2-thalia-en"))


def build_vad() -> silero.VAD:
    return silero.VAD.load()


def build_turn_detection() -> MultilingualModel:
    return MultilingualModel()
