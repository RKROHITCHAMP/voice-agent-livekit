# Conversational Voice Agent — Live Monitoring & Warm Transfer

A voice agent that books appointments over a real-time audio call, can be
**watched and taken over live** from a dashboard, and **warm-transfers** the
caller to a human over the phone via Twilio — then produces a **post-call
summary**.

Built with **LiveKit Agents (Python)**, **OpenAI** (LLM), **Deepgram**
(STT + TTS), **Silero** (VAD), a **Next.js** frontend, and **Twilio** SIP for
telephony.

---

## ✨ What it does

| Capability | How |
|---|---|
| **Natural conversation** | LiveKit `AgentSession` (STT → LLM → TTS) with turn detection and interruption handling. |
| **Appointment booking** | Agent A collects name, reason, date/time, phone → `check_availability` tool → `book_appointment` tool → reads the booking back. Stored in SQLite. |
| **Live monitoring** | Agent streams structured events (transcript, state, intent, action, status) over a LiveKit **data channel**; the Next.js dashboard renders them in real time. |
| **Take over** | The watcher clicks **Take over** → the agent pauses (mic input disabled, speech interrupted) and the watcher's microphone is opened to the caller. **Hand back** resumes the agent. |
| **Warm transfer** | Agent dials a human's phone via Twilio SIP into a private room, reads a spoken summary, asks accept/decline (voice **or** DTMF 1/2). Accept → caller is moved to the human and the agent exits. Decline → agent returns and says the team is unavailable. |
| **Post-call summary** | When the caller hangs up, the LLM produces a structured summary; it's shown in the dashboard and persisted to SQLite. |

---

## 🏗️ Architecture

```
                ┌─────────────────────────── LiveKit Room ───────────────────────────┐
                │                                                                     │
  Browser       │   ┌────────────┐      audio       ┌───────────────────────────┐    │
  (caller)  ◀───┼──▶│  Caller    │◀────────────────▶│   Agent A (Python worker) │    │
  /call         │   │  track     │                  │   AgentSession            │    │
                │   └────────────┘                  │   • Deepgram STT          │    │
                │                                    │   • OpenAI LLM + tools    │    │
                │   ┌────────────┐  data: "monitor"  │   • Deepgram TTS          │    │
  Browser   ◀───┼──▶│  Monitor   │◀──────────────────│   • Silero VAD            │    │
  (watcher)     │   │  (no mic   │  data: "control"  │                           │    │
  /monitor      │   │   until    │──────────────────▶│   booking_agent.py        │    │
                │   │  takeover) │   takeover/resume │   monitoring.py           │    │
                │   └────────────┘                   └─────────────┬─────────────┘    │
                └──────────────────────────────────────────────────┼─────────────────┘
                                                                    │ warm transfer
                                                  SIP (LiveKit)      ▼  (warm_transfer.py)
                                              ┌─────────────────────────────┐
                                              │  Twilio Elastic SIP Trunk    │──▶ ☎ Human agent
                                              └─────────────────────────────┘
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the sequence diagrams of
each flow.

```
voice-agent-livekit/
├── backend/                 # Python LiveKit Agents worker
│   ├── agent.py             # worker entrypoint: session, monitoring hooks, takeover, summary
│   ├── booking_agent.py     # Agent A + function tools (availability, booking, request_human)
│   ├── warm_transfer.py     # Twilio SIP warm-transfer consultation flow
│   ├── monitoring.py        # data-channel event protocol (publisher + control parser)
│   ├── summary.py           # LLM spoken briefing + post-call summary
│   ├── providers.py         # STT / LLM / TTS / VAD factory (swap providers here)
│   ├── db.py                # SQLite appointment + summary store
│   ├── api_server.py        # optional FastAPI: /summary, /bookings, /token
│   └── tests/test_db.py     # unit tests (no external services)
├── frontend/                # Next.js (App Router, TS, Tailwind)
│   ├── app/call/            # caller UI
│   ├── app/monitor/         # live dashboard + take-over
│   ├── app/api/token/       # LiveKit token minting
│   └── lib/monitor-events.ts# TS mirror of the event protocol
└── docs/                    # Twilio setup + architecture
```

---

## ✅ Prerequisites

- **Python 3.10+** and **Node.js 18+**
- A **LiveKit Cloud** project (free) — https://cloud.livekit.io
- An **OpenAI** API key — https://platform.openai.com
- A **Deepgram** API key (free credits) — https://console.deepgram.com
- For warm transfer only: a **Twilio** account (free trial) + the
  [LiveKit CLI](https://docs.livekit.io/home/cli/cli-setup/) (`lk`)

> The conversation, booking, monitoring and take-over flows work with **no
> Twilio at all**. Twilio is only needed for the warm-transfer leg.

---

## 🔑 1. Get your keys

**LiveKit** → Cloud dashboard → *Settings → Keys*: copy the **WS URL**,
**API Key**, **API Secret**.

**OpenAI** → *API keys* → create a key.

**Deepgram** → *API Keys* → create a key.

**Twilio** (warm transfer) → follow [`docs/TWILIO_SETUP.md`](docs/TWILIO_SETUP.md)
to create an Elastic SIP Trunk, register it with LiveKit
(`lk sip outbound create`), and enable **Call Transfer (SIP REFER)** +
**PSTN Transfer**. You'll get a `SIP_OUTBOUND_TRUNK_ID` (starts with `ST_`).

---

## ▶️ 2. Run the backend (agent worker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then fill in your keys

# one-time: download the turn-detector / VAD model files
python agent.py download-files

# start the worker (hot reload)
python agent.py dev
```

The worker connects to LiveKit and waits to be dispatched into a room. Leave it
running.

*(Optional)* run the helper API for summaries/bookings:
```bash
uvicorn api_server:app --reload --port 8080
```

---

## ▶️ 3. Run the frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local     # fill in the same LiveKit values
npm run dev
```

Open **http://localhost:3000**.

- **`/call`** — click *Start call*, allow the mic, and talk to Riley.
- **`/monitor`** — open in a second tab/window to watch live and take over.

Both join the same room (`NEXT_PUBLIC_DEFAULT_ROOM`), so the agent, caller and
watcher all meet automatically.

---

## 🗣️ Flow walkthroughs

### Conversation & booking
Agent A (Riley) greets the caller and collects the booking fields one at a
time. Before confirming it calls **`check_availability(date, time)`** against
SQLite (a few slots are pre-seeded as "busy" so you can see it offer
alternatives). Once a slot is free and read back, it calls
**`book_appointment(...)`**, persists the row, and confirms out loud. Relative
dates like "tomorrow" are resolved by the LLM against today's date injected into
the system prompt.

### Live monitoring
On every meaningful step the agent publishes a JSON event on the **`monitor`**
data topic:
`transcript` (caller/agent, interim + final), `state`
(listening/thinking/speaking), `intent` (booking / human_handoff / general),
`action` (`checking_availability`, `booking`, `transferring`…), `status`
(connected/transferring/ended) and finally `summary`. The dashboard subscribes
to that topic and renders the transcript, the agent's current state, detected
intent, an action feed, and call status — all live.

### Take over
The watcher's browser is already in the room (muted). Clicking **Take over**:
1. publishes `{command:"takeover"}` on the **`control`** topic, and
2. enables the watcher's microphone.

The agent receives the control message and calls
`session.input.set_audio_enabled(False)` + `session.interrupt()` — it stops
listening and speaking. Caller and watcher now talk directly (same room, WebRTC
audio). **Hand back** reverses it: mic off, `{command:"resume"}`, agent
re-enabled.

### Warm transfer (Twilio)
When the caller asks for a person (or for billing/complaints), the LLM calls
**`request_human(reason)`**. `warm_transfer.py` then:
1. generates a 2–3 sentence spoken briefing from the transcript,
2. creates a private transfer room and **dials the human's phone via Twilio
   SIP** into it,
3. runs a small consultation agent that reads the briefing and asks the human
   to **accept (say "yes" / press 1)** or **decline (say "no" / press 2)**,
4. **Accept** → the human is `MoveParticipant`-ed into the caller's room, Agent
   A says goodbye and disconnects, leaving caller + human connected.
   **Decline / no-answer** → the transfer room is torn down and Agent A tells
   the caller the team isn't available right now.

### Post-call summary
When the caller leaves (or on worker shutdown) the LLM produces a structured
summary (intent / details / outcome / follow-up / sentiment). It's published
live to the dashboard and saved to SQLite (`GET /summary/{room}` via the helper
API).

---

## 🧪 Tests

```bash
cd backend
pip install pytest
pytest -q          # booking-store logic, no external services needed
```

---

## 🔧 Swapping providers

Everything provider-specific lives in **`backend/providers.py`**. To use Groq,
ElevenLabs, Cartesia, OpenAI Realtime, etc., change the constructors there and
add the matching `livekit-plugins-*` extra to `requirements.txt`. Nothing else
in the codebase imports a provider directly.

---

## 🩹 Troubleshooting

- **Agent never joins the room** — the worker (`python agent.py dev`) must be
  running and pointed at the same LiveKit project as the frontend.
- **No audio** — check browser mic permissions; the caller page needs mic
  access and the page must be served over `localhost`/HTTPS.
- **Transfer fails immediately** — `SIP_OUTBOUND_TRUNK_ID` /
  `HUMAN_AGENT_NUMBER` not set, or SIP REFER/PSTN transfer not enabled on the
  Twilio trunk (see `docs/TWILIO_SETUP.md`). On a Twilio **trial** account you
  can only call **verified** numbers.
- **`download-files` errors** — run it once before `dev`; it fetches the
  turn-detector and VAD models.

---

## 📜 License

MIT — see [`LICENSE`](LICENSE).
