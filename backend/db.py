"""
SQLite-backed appointment store.

Two things the booking agent needs:
  * check_availability(date, time)  -> is this slot free?
  * book_appointment(...)           -> persist a confirmed booking.

We pre-seed a small set of "busy" slots so the availability check is
demonstrably real (the agent will sometimes have to offer an alternative),
and we keep everything in a single file DB so the project runs with zero
external setup.

All functions are synchronous + cheap; we wrap them in asyncio.to_thread at
the call site so they never block the agent's event loop.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

DB_PATH = os.getenv("APPOINTMENTS_DB", "appointments.db")

# Clinic working hours used to sanity-check requested times.
OPEN_HOUR = 9
CLOSE_HOUR = 18


@dataclass
class Appointment:
    id: str
    name: str
    reason: str
    date: str          # ISO date, e.g. 2026-07-01
    time: str          # 24h "HH:MM"
    phone: str
    created_at: str


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables and seed a couple of already-taken slots."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                reason      TEXT NOT NULL,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                phone       TEXT NOT NULL,
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS summaries (
                room        TEXT PRIMARY KEY,
                summary     TEXT NOT NULL,
                booking     TEXT,
                created_at  TEXT NOT NULL
            )
            """
        )
        # Seed a few "busy" demo slots if the table is empty so that
        # check_availability has something to bump into.
        count = conn.execute("SELECT COUNT(*) AS c FROM appointments").fetchone()["c"]
        if count == 0:
            seed = [
                ("Existing Patient", "follow-up", "2026-07-01", "10:00", "+10000000001"),
                ("Existing Patient", "consultation", "2026-07-01", "14:30", "+10000000002"),
                ("Existing Patient", "check-up", "2026-07-02", "11:00", "+10000000003"),
            ]
            for name, reason, date, time, phone in seed:
                conn.execute(
                    "INSERT INTO appointments VALUES (?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), name, reason, date, time, phone,
                     datetime.utcnow().isoformat()),
                )
        conn.commit()


def _valid_time(time_str: str) -> bool:
    try:
        hh, mm = time_str.split(":")
        hour = int(hh)
        minute = int(mm)
    except (ValueError, AttributeError):
        return False
    if minute not in (0, 15, 30, 45):
        return False
    return OPEN_HOUR <= hour < CLOSE_HOUR


def is_available(date: str, time: str) -> bool:
    """Return True if the slot is within working hours and not taken."""
    if not _valid_time(time):
        return False
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM appointments WHERE date = ? AND time = ? LIMIT 1",
            (date, time),
        ).fetchone()
    return row is None


def suggest_alternatives(date: str, time: str, limit: int = 3) -> list[str]:
    """Offer up to `limit` free times on the requested date."""
    candidates = [
        f"{h:02d}:{m:02d}"
        for h in range(OPEN_HOUR, CLOSE_HOUR)
        for m in (0, 30)
    ]
    free = [t for t in candidates if t != time and is_available(date, t)]
    return free[:limit]


def book(name: str, reason: str, date: str, time: str, phone: str) -> Optional[Appointment]:
    """Persist a booking. Returns the Appointment, or None if the slot
    was taken in the meantime (race-safe re-check)."""
    if not is_available(date, time):
        return None
    appt = Appointment(
        id=str(uuid.uuid4()),
        name=name,
        reason=reason,
        date=date,
        time=time,
        phone=phone,
        created_at=datetime.utcnow().isoformat(),
    )
    with _connect() as conn:
        conn.execute(
            "INSERT INTO appointments VALUES (?,?,?,?,?,?,?)",
            (appt.id, appt.name, appt.reason, appt.date, appt.time,
             appt.phone, appt.created_at),
        )
        conn.commit()
    return appt


def to_dict(appt: Appointment) -> dict:
    return asdict(appt)


def save_summary(room: str, summary_text: str, booking: Optional[dict]) -> None:
    """Persist a post-call summary so the dashboard can fetch it after the
    room has closed."""
    import json
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO summaries VALUES (?,?,?,?)",
            (
                room,
                summary_text,
                json.dumps(booking) if booking else None,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_summary(room: str) -> Optional[dict]:
    import json
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM summaries WHERE room = ?", (room,)
        ).fetchone()
    if row is None:
        return None
    return {
        "room": row["room"],
        "summary": row["summary"],
        "booking": json.loads(row["booking"]) if row["booking"] else None,
        "created_at": row["created_at"],
    }


if __name__ == "__main__":
    # Quick smoke test:  python db.py
    init_db()
    print("2026-07-01 10:00 free?", is_available("2026-07-01", "10:00"))  # False (seeded)
    print("2026-07-01 09:30 free?", is_available("2026-07-01", "09:30"))  # True
    print("alternatives:", suggest_alternatives("2026-07-01", "10:00"))
    a = book("Test User", "cleaning", "2026-07-03", "09:30", "+15551234567")
    print("booked:", a)
