"use client";

import {
  LiveKitRoom,
  RoomAudioRenderer,
  BarVisualizer,
  useVoiceAssistant,
  useLocalParticipant,
  useConnectionState,
  useRoomContext,
} from "@livekit/components-react";
import { ConnectionState } from "livekit-client";
import Link from "next/link";
import { useState } from "react";
import { useToken } from "@/lib/useToken";

const ROOM = process.env.NEXT_PUBLIC_DEFAULT_ROOM || "voice-agent-room";

export default function CallPage() {
  const { info, error } = useToken("caller", ROOM);
  const [connect, setConnect] = useState(false);

  if (error)
    return <ErrorBox msg={`Could not get a token: ${error}`} />;

  return (
    <main className="space-y-6">
      <TopBar />
      {!info ? (
        <p className="text-slate-400">Preparing call…</p>
      ) : (
        <LiveKitRoom
          serverUrl={info.url}
          token={info.token}
          connect={connect}
          audio={true}
          video={false}
          onDisconnected={() => setConnect(false)}
          className="card"
        >
          <RoomAudioRenderer />
          <CallInner connect={connect} onConnect={() => setConnect(true)} />
        </LiveKitRoom>
      )}
    </main>
  );
}

function CallInner({
  connect,
  onConnect,
}: {
  connect: boolean;
  onConnect: () => void;
}) {
  const state = useConnectionState();
  const room = useRoomContext();
  const { state: agentState, audioTrack } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();

  if (!connect || state === ConnectionState.Disconnected) {
    return (
      <div className="flex flex-col items-center gap-4 py-10">
        <p className="text-slate-300">
          You&apos;ll be connected to <b>Riley</b>, the clinic&apos;s voice
          receptionist.
        </p>
        <button
          onClick={onConnect}
          className="rounded-lg bg-sky-500 px-6 py-3 font-medium text-white hover:bg-sky-400"
        >
          Start call
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6 py-8">
      <span className="pill bg-emerald-500/15 text-emerald-300">
        ● {labelForState(agentState)}
      </span>

      <div className="h-28 w-full max-w-md">
        <BarVisualizer
          state={agentState}
          trackRef={audioTrack}
          barCount={7}
          className="h-full"
        />
      </div>

      <div className="flex gap-3">
        <button
          onClick={() =>
            localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)
          }
          className="rounded-lg border border-edge px-4 py-2 text-sm hover:border-sky-500"
        >
          {isMicrophoneEnabled ? "🎙️ Mute" : "🔇 Unmute"}
        </button>
        <button
          onClick={() => room.disconnect()}
          className="rounded-lg bg-rose-500/90 px-4 py-2 text-sm font-medium text-white hover:bg-rose-500"
        >
          End call
        </button>
      </div>

      <p className="text-xs text-slate-500">
        Try: “I&apos;d like to book an appointment” or “Can I speak to a
        person?”
      </p>
    </div>
  );
}

function labelForState(s: string) {
  switch (s) {
    case "listening":
      return "Listening";
    case "thinking":
      return "Thinking";
    case "speaking":
      return "Speaking";
    default:
      return "Connecting";
  }
}

function TopBar() {
  return (
    <div className="flex items-center justify-between">
      <h1 className="text-2xl font-semibold">📞 Call Agent A</h1>
      <Link href="/monitor" className="text-sm text-sky-400 hover:underline">
        Open live monitor →
      </Link>
    </div>
  );
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="card border-rose-500/40 text-rose-300">
      <p>{msg}</p>
      <p className="mt-2 text-xs text-slate-400">
        Check that <code>LIVEKIT_*</code> vars are set in{" "}
        <code>.env.local</code> and restart <code>npm run dev</code>.
      </p>
    </div>
  );
}
