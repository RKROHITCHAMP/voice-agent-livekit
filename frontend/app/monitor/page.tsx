"use client";

import {
  LiveKitRoom,
  RoomAudioRenderer,
  useRoomContext,
  useLocalParticipant,
} from "@livekit/components-react";
import { RoomEvent } from "livekit-client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useToken } from "@/lib/useToken";
import {
  AgentStateValue,
  CallStatusValue,
  MONITOR_TOPIC,
  MonitorEvent,
  TranscriptEvent,
  encodeControl,
  parseMonitorEvent,
} from "@/lib/monitor-events";

const ROOM = process.env.NEXT_PUBLIC_DEFAULT_ROOM || "voice-agent-room";

export default function MonitorPage() {
  const { info, error } = useToken("monitor", ROOM);

  if (error)
    return (
      <div className="card border-rose-500/40 text-rose-300">
        Could not get a token: {error}
      </div>
    );

  return (
    <main className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">🖥️ Live Call Monitor</h1>
        <Link href="/call" className="text-sm text-sky-400 hover:underline">
          ← Back to call
        </Link>
      </div>

      {!info ? (
        <p className="text-slate-400">Connecting to room…</p>
      ) : (
        <LiveKitRoom
          serverUrl={info.url}
          token={info.token}
          connect={true}
          audio={false}
          video={false}
        >
          <RoomAudioRenderer />
          <Dashboard />
        </LiveKitRoom>
      )}
    </main>
  );
}

type Action = { action: string; detail: string; ts: number };

function Dashboard() {
  const room = useRoomContext();
  const { localParticipant } = useLocalParticipant();

  const [transcript, setTranscript] = useState<TranscriptEvent[]>([]);
  const [agentState, setAgentState] = useState<AgentStateValue>("idle");
  const [intent, setIntent] = useState<string>("—");
  const [actions, setActions] = useState<Action[]>([]);
  const [status, setStatus] = useState<CallStatusValue>("connected");
  const [summary, setSummary] = useState<string | null>(null);
  const [booking, setBooking] = useState<Record<string, unknown> | null>(null);
  const [taken, setTaken] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  // Subscribe to monitoring events on the data channel.
  useEffect(() => {
    const onData = (
      payload: Uint8Array,
      _p: unknown,
      _k: unknown,
      topic?: string
    ) => {
      if (topic !== MONITOR_TOPIC) return;
      const ev = parseMonitorEvent(payload);
      if (!ev) return;
      applyEvent(ev);
    };
    room.on(RoomEvent.DataReceived, onData as never);
    return () => {
      room.off(RoomEvent.DataReceived, onData as never);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room]);

  function applyEvent(ev: MonitorEvent) {
    switch (ev.type) {
      case "transcript":
        setTranscript((prev) => {
          // Replace a trailing non-final line from the same role (interim).
          const last = prev[prev.length - 1];
          if (last && !last.final && last.role === ev.role) {
            return [...prev.slice(0, -1), ev];
          }
          return [...prev, ev];
        });
        break;
      case "state":
        setAgentState(ev.state);
        break;
      case "intent":
        setIntent(ev.intent);
        break;
      case "action":
        setActions((prev) => [
          { action: ev.action, detail: ev.detail, ts: ev.ts },
          ...prev,
        ].slice(0, 8));
        break;
      case "status":
        setStatus(ev.status);
        break;
      case "summary":
        setSummary(ev.summary);
        setBooking(ev.booking);
        break;
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  async function takeOver() {
    await localParticipant.setMicrophoneEnabled(true);
    await localParticipant.publishData(encodeControl("takeover"), {
      reliable: true,
      topic: "control",
    });
    setTaken(true);
  }

  async function handBack() {
    await localParticipant.setMicrophoneEnabled(false);
    await localParticipant.publishData(encodeControl("resume"), {
      reliable: true,
      topic: "control",
    });
    setTaken(false);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {/* Left: live transcript */}
      <section className="card lg:col-span-2 flex flex-col h-[70vh]">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
          Live transcript
        </h2>
        <div className="flex-1 space-y-3 overflow-y-auto pr-2">
          {transcript.length === 0 && (
            <p className="text-slate-500 text-sm">
              Waiting for the conversation to start…
            </p>
          )}
          {transcript.map((t, i) => (
            <Bubble key={i} t={t} />
          ))}
          <div ref={bottomRef} />
        </div>
      </section>

      {/* Right: state + controls */}
      <section className="space-y-4">
        <StatePanel
          status={status}
          agentState={agentState}
          intent={intent}
          taken={taken}
        />

        <ActionFeed actions={actions} />

        <div className="card space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            Watcher control
          </h3>
          {!taken ? (
            <button
              onClick={takeOver}
              disabled={status === "ended"}
              className="w-full rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400 disabled:opacity-40"
            >
              ✋ Take over call
            </button>
          ) : (
            <button
              onClick={handBack}
              className="w-full rounded-lg bg-sky-500 px-4 py-2 font-medium text-white hover:bg-sky-400"
            >
              ↩︎ Hand back to agent
            </button>
          )}
          <p className="text-xs text-slate-500">
            Taking over pauses the agent and opens your mic to the caller.
          </p>
        </div>

        {summary && <SummaryCard summary={summary} booking={booking} />}
      </section>
    </div>
  );
}

function Bubble({ t }: { t: TranscriptEvent }) {
  const styles: Record<string, string> = {
    caller: "bg-slate-700/40 border-slate-600",
    agent: "bg-sky-500/10 border-sky-700",
    watcher: "bg-amber-500/10 border-amber-600",
  };
  const labels: Record<string, string> = {
    caller: "Caller",
    agent: "Agent",
    watcher: "Watcher",
  };
  return (
    <div className={`rounded-lg border px-3 py-2 ${styles[t.role]}`}>
      <div className="text-[10px] uppercase tracking-wide text-slate-400">
        {labels[t.role]} {!t.final && <span className="italic">(typing…)</span>}
      </div>
      <div className="text-sm">{t.text}</div>
    </div>
  );
}

function StatePanel({
  status,
  agentState,
  intent,
  taken,
}: {
  status: CallStatusValue;
  agentState: AgentStateValue;
  intent: string;
  taken: boolean;
}) {
  const statusColor: Record<CallStatusValue, string> = {
    connected: "bg-emerald-500/15 text-emerald-300",
    transferring: "bg-amber-500/15 text-amber-300",
    ended: "bg-slate-500/20 text-slate-300",
  };
  const stateColor: Record<string, string> = {
    listening: "bg-emerald-500/15 text-emerald-300",
    thinking: "bg-violet-500/15 text-violet-300",
    speaking: "bg-sky-500/15 text-sky-300",
    human_controlled: "bg-amber-500/15 text-amber-300",
    idle: "bg-slate-500/20 text-slate-300",
  };
  return (
    <div className="card space-y-3">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
        Status
      </h3>
      <Row label="Call">
        <span className={`pill ${statusColor[status]}`}>● {status}</span>
      </Row>
      <Row label="Agent">
        <span className={`pill ${stateColor[agentState]}`}>
          ● {taken ? "human_controlled" : agentState}
        </span>
      </Row>
      <Row label="Intent">
        <span className="pill bg-slate-700/50 text-slate-200">{intent}</span>
      </Row>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </div>
  );
}

function ActionFeed({ actions }: { actions: Action[] }) {
  const pretty: Record<string, string> = {
    checking_availability: "Checking availability…",
    booking: "Booking…",
    booked: "Appointment booked ✓",
    transferring: "Transferring to a human…",
    transfer_failed: "Transfer failed",
  };
  return (
    <div className="card space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
        Actions
      </h3>
      {actions.length === 0 ? (
        <p className="text-xs text-slate-500">No actions yet.</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {actions.map((a, i) => (
            <li key={i} className="flex justify-between gap-2">
              <span>{pretty[a.action] || a.action}</span>
              {a.detail && (
                <span className="text-xs text-slate-500">{a.detail}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SummaryCard({
  summary,
  booking,
}: {
  summary: string;
  booking: Record<string, unknown> | null;
}) {
  return (
    <div className="card border-emerald-700/50">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-emerald-300">
        Post-call summary
      </h3>
      <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-200">
        {summary}
      </pre>
      {booking && (
        <div className="mt-3 rounded-lg bg-emerald-500/10 p-2 text-xs text-emerald-200">
          📅 Booked: {String(booking.name)} · {String(booking.date)}{" "}
          {String(booking.time)} · {String(booking.reason)}
        </div>
      )}
    </div>
  );
}
