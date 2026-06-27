import { useEffect, useState } from "react";

export type TokenInfo = { token: string; url: string; room: string; identity: string };

// Fetches a LiveKit token from the Next.js /api/token route.
export function useToken(role: "caller" | "monitor", room?: string) {
  const [info, setInfo] = useState<TokenInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ role });
    if (room) params.set("room", room);
    fetch(`/api/token?${params.toString()}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).error || "token error");
        return r.json();
      })
      .then(setInfo)
      .catch((e) => setError(e.message));
  }, [role, room]);

  return { info, error };
}
