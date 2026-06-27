"""
Optional helper HTTP API (FastAPI).

The Next.js app mints its own LiveKit tokens, so this server is NOT required to
run the demo. It's handy for:
  * GET /summary/{room}  -> fetch a post-call summary after the room closed.
  * GET /bookings        -> inspect appointments stored in SQLite.
  * POST /token          -> mint a token (alternative to the Next.js route).
  * GET /healthz         -> liveness.

Run with:  uvicorn api_server:app --reload --port 8080
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel

import db

load_dotenv()

app = FastAPI(title="Voice Agent Helper API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


class TokenRequest(BaseModel):
    room: str
    identity: str
    name: str | None = None
    can_publish: bool = True


@app.post("/token")
def mint_token(req: TokenRequest) -> dict:
    key = os.getenv("LIVEKIT_API_KEY")
    secret = os.getenv("LIVEKIT_API_SECRET")
    if not key or not secret:
        raise HTTPException(500, "LiveKit credentials not configured")
    token = (
        api.AccessToken(key, secret)
        .with_identity(req.identity)
        .with_name(req.name or req.identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=req.room,
                can_publish=req.can_publish,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )
    return {"token": token, "url": os.getenv("LIVEKIT_URL")}


@app.get("/summary/{room}")
def get_summary(room: str) -> dict:
    s = db.get_summary(room)
    if s is None:
        raise HTTPException(404, "summary not ready")
    return s


@app.get("/bookings")
def list_bookings() -> dict:
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM appointments ORDER BY date, time"
    ).fetchall()
    conn.close()
    return {"bookings": [dict(r) for r in rows]}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
