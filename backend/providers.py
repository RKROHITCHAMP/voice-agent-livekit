"""
Central place that wires up the AI providers so both the main booking
session and the warm-transfer consultation session use identical config.

Stack (all have free tiers, all first-class in LiveKit Agents):
  * LLM : OpenAI            (conversation, intent, summaries)
  * STT : Deepgram nova-3
  * TTS : Deepgram Aura-2
  * VAD : Silero            (local, free, no API key)
  * Turn detection : LiveKit multilingual turn detector (local)

Swap any of these by editing this one file — nothing else references the
provider classes directly.
"""
from __future__ import annotations

import os

from livekit.plugins import deepgram, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel


def build_llm() -> openai.LLM:
    return openai.LLM(model=os.getenv("LLM_MODEL", "gpt-4o-mini"))


def build_stt() -> deepgram.STT:
    return deepgram.STT(model=os.getenv("STT_MODEL", "nova-3"), language="multi")


def build_tts() -> deepgram.TTS:
    return deepgram.TTS(model=os.getenv("TTS_VOICE", "aura-2-thalia-en"))


def build_vad() -> silero.VAD:
    return silero.VAD.load()


def build_turn_detection() -> MultilingualModel:
    return MultilingualModel()
