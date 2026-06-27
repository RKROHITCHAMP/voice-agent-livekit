import { NextRequest, NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";

// Mints a LiveKit access token for a participant.
// Query params:
//   room      - room name (defaults to NEXT_PUBLIC_DEFAULT_ROOM)
//   identity  - participant identity (required)
//   name      - display name (optional)
//   role      - "caller" | "monitor"  (monitor identities are prefixed so the
//               agent can tell them apart from the caller)
export async function GET(req: NextRequest) {
  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const wsUrl = process.env.NEXT_PUBLIC_LIVEKIT_URL || process.env.LIVEKIT_URL;

  if (!apiKey || !apiSecret || !wsUrl) {
    return NextResponse.json(
      { error: "LiveKit env vars not configured" },
      { status: 500 }
    );
  }

  const { searchParams } = new URL(req.url);
  const room =
    searchParams.get("room") ||
    process.env.NEXT_PUBLIC_DEFAULT_ROOM ||
    "voice-agent-room";
  const role = searchParams.get("role") === "monitor" ? "monitor" : "caller";
  const rawIdentity =
    searchParams.get("identity") ||
    `${role}-${Math.random().toString(36).slice(2, 8)}`;
  // Prefix monitor identities so the backend never mistakes a watcher for the
  // caller when deciding to end the call.
  const identity =
    role === "monitor" && !rawIdentity.startsWith("monitor")
      ? `monitor-${rawIdentity}`
      : rawIdentity;
  const name = searchParams.get("name") || identity;

  const at = new AccessToken(apiKey, apiSecret, { identity, name });
  at.addGrant({
    room,
    roomJoin: true,
    canPublish: true, // monitor needs publish rights to take over with mic
    canSubscribe: true,
    canPublishData: true,
  });

  const token = await at.toJwt();
  return NextResponse.json({ token, url: wsUrl, room, identity });
}
