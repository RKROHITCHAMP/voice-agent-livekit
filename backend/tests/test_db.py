"""
Unit tests for the booking store. Run with:  pytest -q
These run with zero external services (pure SQLite).
"""
import os
import tempfile

import pytest


@pytest.fixture()
def fresh_db(monkeypatch):
    # Point the DB at a throwaway file and reload the module so it picks it up.
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("APPOINTMENTS_DB", tmp.name)
    import importlib
    import db as db_module
    importlib.reload(db_module)
    db_module.init_db()
    yield db_module
    os.unlink(tmp.name)


def test_seeded_slot_is_taken(fresh_db):
    assert fresh_db.is_available("2026-07-01", "10:00") is False


def test_open_slot_is_available(fresh_db):
    assert fresh_db.is_available("2026-07-01", "09:30") is True


def test_outside_hours_rejected(fresh_db):
    assert fresh_db.is_available("2026-07-01", "08:00") is False  # before open
    assert fresh_db.is_available("2026-07-01", "19:00") is False  # after close


def test_book_then_unavailable(fresh_db):
    appt = fresh_db.book("Jane Doe", "checkup", "2026-07-05", "11:30", "+15551112222")
    assert appt is not None
    assert fresh_db.is_available("2026-07-05", "11:30") is False


def test_double_book_returns_none(fresh_db):
    fresh_db.book("A", "x", "2026-07-06", "12:00", "+1")
    assert fresh_db.book("B", "y", "2026-07-06", "12:00", "+2") is None


def test_alternatives_excludes_requested(fresh_db):
    alts = fresh_db.suggest_alternatives("2026-07-01", "10:00")
    assert "10:00" not in alts
    assert all(fresh_db.is_available("2026-07-01", t) for t in alts)


def test_summary_roundtrip(fresh_db):
    fresh_db.save_summary("room-1", "All good.", {"name": "Jane"})
    got = fresh_db.get_summary("room-1")
    assert got["summary"] == "All good."
    assert got["booking"]["name"] == "Jane"
