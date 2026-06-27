// TypeScript mirror of backend/monitoring.py event shapes.
// Keep these two files in sync.

export type AgentStateValue =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "human_controlled";

export type CallStatusValue = "connected" | "transferring" | "ended";

export type TranscriptEvent = {
  type: "transcript";
  role: "caller" | "agent" | "watcher";
  text: string;
  final: boolean;
  ts: number;
};

export type StateEvent = { type: "state"; state: AgentStateValue; ts: number };
export type IntentEvent = {
  type: "intent";
  intent: string;
  confidence: number | null;
  ts: number;
};
export type ActionEvent = {
  type: "action";
  action: string;
  detail: string;
  ts: number;
};
export type StatusEvent = { type: "status"; status: CallStatusValue; ts: number };
export type SummaryEvent = {
  type: "summary";
  summary: string;
  booking: Record<string, unknown> | null;
  ts: number;
};

export type MonitorEvent =
  | TranscriptEvent
  | StateEvent
  | IntentEvent
  | ActionEvent
  | StatusEvent
  | SummaryEvent;

export const MONITOR_TOPIC = "monitor";
export const CONTROL_TOPIC = "control";

export function parseMonitorEvent(bytes: Uint8Array): MonitorEvent | null {
  try {
    const obj = JSON.parse(new TextDecoder().decode(bytes));
    if (obj && typeof obj.type === "string") return obj as MonitorEvent;
  } catch {
    /* ignore malformed packets */
  }
  return null;
}

export function encodeControl(command: "takeover" | "resume"): Uint8Array {
  return new TextEncoder().encode(JSON.stringify({ command }));
}
