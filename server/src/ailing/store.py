"""SQLite storage. Only the latest lexicon snapshot is kept (docs/architecture.md, Lexicon)."""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from ailing.gateway import AnkiUnavailable, CallTool
from ailing.lexicon import Entry, fetch_snapshot

SNAPSHOT_MAX_AGE = timedelta(hours=24)

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lexicon (
    note_id INTEGER PRIMARY KEY,
    entry TEXT NOT NULL,
    meaning TEXT NOT NULL,
    tier TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def save_snapshot(conn: sqlite3.Connection, entries: list[Entry], taken_at: datetime) -> None:
    """Replaces the whole snapshot in one transaction, so a reader never sees half of one."""
    with conn:
        conn.execute("DELETE FROM lexicon")
        conn.executemany(
            "INSERT INTO lexicon (note_id, entry, meaning, tier) VALUES (?, ?, ?, ?)",
            [(e.note_id, e.text, e.meaning, e.tier) for e in entries],
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('snapshot_taken_at', ?)",
            (taken_at.isoformat(),),
        )


def load_snapshot(conn: sqlite3.Connection) -> tuple[list[Entry], datetime | None]:
    rows = conn.execute("SELECT note_id, entry, meaning, tier FROM lexicon ORDER BY note_id")
    entries = [Entry(note_id, entry, meaning, tier) for note_id, entry, meaning, tier in rows]
    row = conn.execute("SELECT value FROM meta WHERE key = 'snapshot_taken_at'").fetchone()
    return entries, datetime.fromisoformat(row[0]) if row else None


def is_stale(taken_at: datetime | None, now: datetime) -> bool:
    return taken_at is None or now - taken_at >= SNAPSHOT_MAX_AGE


async def refresh_if_stale(conn: sqlite3.Connection, call: CallTool, now: datetime) -> bool:
    """Takes a new snapshot when the last one is a day old. If Anki can't be reached, the old
    snapshot stays in place and the app keeps running on it. Returns whether it refreshed."""
    _, taken_at = load_snapshot(conn)
    if not is_stale(taken_at, now):
        return False
    try:
        entries = await fetch_snapshot(call)
    except AnkiUnavailable as e:
        log.warning("Lexicon not refreshed, using the snapshot from %s: %s", taken_at, e)
        return False
    if not entries:
        log.warning("Anki returned no Thai notes; keeping the snapshot from %s", taken_at)
        return False
    save_snapshot(conn, entries, now)
    return True
