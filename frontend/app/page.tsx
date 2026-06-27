import Link from "next/link";

export default function Home() {
  return (
    <main className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">Conversational Voice Agent</h1>
        <p className="text-slate-400">
          Book appointments by voice, watch the conversation live, take over,
          and warm-transfer to a human — built on LiveKit, OpenAI, Deepgram and
          Twilio.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <Link href="/call" className="card hover:border-sky-500 transition">
          <h2 className="text-xl font-medium">📞 Start a call</h2>
          <p className="mt-2 text-sm text-slate-400">
            Talk to Agent A (Riley). Book an appointment or ask to speak to a
            person.
          </p>
        </Link>

        <Link href="/monitor" className="card hover:border-sky-500 transition">
          <h2 className="text-xl font-medium">🖥️ Live monitor</h2>
          <p className="mt-2 text-sm text-slate-400">
            Watch the transcript and agent state in real time, take over the
            call, and read the post-call summary.
          </p>
        </Link>
      </div>

      <p className="text-xs text-slate-500">
        Make sure the Python agent worker is running
        (<code className="text-slate-300">python agent.py dev</code>) and your
        LiveKit keys are set in <code className="text-slate-300">.env.local</code>.
      </p>
    </main>
  );
}
