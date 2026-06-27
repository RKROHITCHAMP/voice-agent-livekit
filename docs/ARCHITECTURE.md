# Architecture & flows

## Components

- **LiveKit room** — the meeting point for the caller, the agent worker, and
  the watcher. Carries audio (WebRTC) and JSON events (data channel).
- **Agent worker** (`backend/`) — a LiveKit Agents `AgentSession` running
  Deepgram STT, OpenAI LLM (+ function tools), Deepgram TTS and Silero VAD.
- **Frontend** (`frontend/`) — Next.js app: a caller page and a monitor
  dashboard. Mints its own LiveKit tokens.
- **Twilio SIP trunk** — used only during a warm transfer to dial a real phone.

## Data-channel event protocol

Two topics on the LiveKit data channel:

| Topic | Direction | Messages |
|---|---|---|
| `monitor` | agent → watcher | `transcript`, `state`, `intent`, `action`, `status`, `summary` |
| `control` | watcher → agent | `{command: "takeover" \| "resume"}` |

Shapes are defined once in `backend/monitoring.py` and mirrored in
`frontend/lib/monitor-events.ts`.

## Booking flow

```mermaid
sequenceDiagram
    participant C as Caller
    participant A as Agent A
    participant DB as SQLite
    participant M as Monitor
    C->>A: "Book an appointment"
    A->>M: intent=booking
    A->>C: asks name / reason / date / time / phone
    C->>A: provides details
    A->>M: action=checking_availability
    A->>DB: is_available(date,time)
    alt slot free
        A->>C: reads details back
        A->>DB: book(...)
        A->>M: action=booked
        A->>C: confirms booking
    else slot taken
        A->>C: offers alternatives
    end
```

## Take-over flow

```mermaid
sequenceDiagram
    participant W as Watcher
    participant A as Agent A
    participant C as Caller
    W->>A: control{takeover} + opens mic
    A->>A: input audio OFF + interrupt()
    A->>W: state=human_controlled
    W<<->>C: talk directly (WebRTC audio)
    W->>A: control{resume} + mic OFF
    A->>A: input audio ON
    A->>C: agent resumes
```

## Warm transfer flow

```mermaid
sequenceDiagram
    participant C as Caller
    participant A as Agent A
    participant T as Transfer room
    participant H as Human (phone)
    C->>A: "talk to a person"
    A->>A: build spoken briefing (LLM)
    A->>T: create room
    A->>H: dial via Twilio SIP
    A->>H: read briefing, ask accept/decline
    alt accept (say yes / press 1)
        A->>C: MoveParticipant(human → caller room)
        A->>C: "you're connected" then disconnect
        C<<->>H: connected
    else decline (say no / press 2 / timeout)
        A->>T: delete room
        A->>C: "team isn't available right now"
    end
```

## End-of-call summary

When the caller participant disconnects (or the worker shuts down), the agent
calls the LLM with the full transcript + any booking, produces a structured
summary, publishes it on the `monitor` topic, and saves it to SQLite
(`summaries` table; readable via `GET /summary/{room}`).
