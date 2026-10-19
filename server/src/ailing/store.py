"""SQLite storage: the lexicon snapshot, topics, generated texts, the reading log, and the difficulty
setting. Only the latest lexicon snapshot is kept (docs/architecture.md, Lexicon)."""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ailing.difficulty import Difficulty
from ailing.gateway import AnkiUnavailable, CallTool
from ailing.generator import MODEL, Generated, Line
from ailing.lexicon import Entry, fetch_snapshot

SNAPSHOT_MAX_AGE = timedelta(hours=24)
LANGUAGE = "thai"
MODE = "read_listen"

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lexicon (
    note_id INTEGER PRIMARY KEY,
    entry TEXT NOT NULL,
    meaning TEXT NOT NULL,
    tier TEXT NOT NULL,
    due INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    favorite INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS texts (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    title TEXT NOT NULL,
    lines TEXT NOT NULL,
    glosses TEXT NOT NULL,
    stretch TEXT NOT NULL,
    coverage REAL NOT NULL,
    token_count INTEGER NOT NULL,
    floor REAL NOT NULL,
    attempts INTEGER NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY,
    text_id INTEGER NOT NULL REFERENCES texts(id),
    logged_at TEXT NOT NULL,
    language TEXT NOT NULL,
    mode TEXT NOT NULL,
    rating TEXT,
    finished INTEGER NOT NULL,
    words_glossed TEXT NOT NULL,
    words_flagged TEXT NOT NULL,
    audio_speed REAL,
    listen_only INTEGER NOT NULL,
    seconds INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Topic:
    id: int
    name: str
    favorite: bool
    ready: int  # texts waiting to be read


@dataclass(frozen=True)
class StoredText:
    id: int
    topic_id: int
    title: str
    lines: tuple[Line, ...]
    glosses: dict[str, str]
    stretch: tuple[str, ...]
    coverage: float


@dataclass(frozen=True)
class Reading:
    rating: str | None  # "too_easy", "about_right" or "too_hard"
    finished: bool
    words_glossed: tuple[str, ...]
    words_flagged: tuple[str, ...]
    audio_speed: float | None
    listen_only: bool
    seconds: int


def connect(path: Path | str) -> sqlite3.Connection:
    # One connection shared by the async handlers, which all run on the event loop's thread.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    with conn:
        # A text left pending by a restart mid-audio: its missing lines are made on request.
        conn.execute("UPDATE texts SET status = 'ready' WHERE status = 'pending'")
    return conn


# ==== Lexicon ====


def save_snapshot(conn: sqlite3.Connection, entries: list[Entry], taken_at: datetime) -> None:
    """Replaces the whole snapshot in one transaction, so a reader never sees half of one."""
    with conn:
        conn.execute("DELETE FROM lexicon")
        conn.executemany(
            "INSERT INTO lexicon (note_id, entry, meaning, tier, due) VALUES (?, ?, ?, ?, ?)",
            [(e.note_id, e.text, e.meaning, e.tier, int(e.due)) for e in entries],
        )
        _set_meta(conn, "snapshot_taken_at", taken_at.isoformat())


def load_snapshot(conn: sqlite3.Connection) -> tuple[list[Entry], datetime | None]:
    rows = conn.execute("SELECT note_id, entry, meaning, tier, due FROM lexicon ORDER BY note_id")
    entries = [
        Entry(nid, entry, meaning, tier, bool(due)) for nid, entry, meaning, tier, due in rows
    ]
    taken_at = _get_meta(conn, "snapshot_taken_at")
    return entries, datetime.fromisoformat(taken_at) if taken_at else None


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


# ==== Topics ====


def add_topic(conn: sqlite3.Connection, name: str, favorite: bool, now: datetime) -> Topic:
    """Adds a topic, or returns the existing one with that name (ignoring case)."""
    name = " ".join(name.split())
    if not name:
        raise ValueError("A topic needs a name")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO topics (name, favorite, created_at) VALUES (?, ?, ?)",
            (name, int(favorite), now.isoformat()),
        )
    row = conn.execute("SELECT id FROM topics WHERE name = ?", (name,)).fetchone()
    topic = get_topic(conn, row[0])
    assert topic is not None
    return topic


def get_topic(conn: sqlite3.Connection, topic_id: int) -> Topic | None:
    return next((t for t in list_topics(conn) if t.id == topic_id), None)


def list_topics(conn: sqlite3.Connection) -> list[Topic]:
    rows = conn.execute(
        """SELECT t.id, t.name, t.favorite,
                  (SELECT COUNT(*) FROM texts x WHERE x.topic_id = t.id AND x.status = 'ready')
           FROM topics t ORDER BY t.favorite DESC, t.name"""
    )
    return [Topic(i, name, bool(fav), ready) for i, name, fav, ready in rows]


def set_favorite(conn: sqlite3.Connection, topic_id: int, favorite: bool) -> Topic | None:
    with conn:
        conn.execute("UPDATE topics SET favorite = ? WHERE id = ?", (int(favorite), topic_id))
    return get_topic(conn, topic_id)


# ==== Texts ====


def save_text(
    conn: sqlite3.Connection,
    topic_id: int,
    generated: Generated,
    stretch: list[str],
    floor: float,
    now: datetime,
    status: str = "ready",
) -> int:
    """Stores a generated text. `status` is "pending" while its audio is made, "ready" once it can
    be served, or "dropped" for a text that missed the floor (kept only for its cost)."""
    u = generated.usage
    with conn:
        cur = conn.execute(
            """INSERT INTO texts (topic_id, created_at, status, title, lines, glosses, stretch,
                   coverage, token_count, floor, attempts, model, input_tokens, output_tokens,
                   cache_read_tokens, cache_write_tokens, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                topic_id,
                now.isoformat(),
                status,
                generated.title,
                json.dumps([ln.__dict__ for ln in generated.lines], ensure_ascii=False),
                json.dumps(generated.glosses, ensure_ascii=False),
                json.dumps(stretch, ensure_ascii=False),
                generated.coverage.ratio,
                generated.coverage.counted,
                floor,
                generated.attempts,
                u.model or MODEL,
                u.input_tokens,
                u.output_tokens,
                u.cache_read_tokens,
                u.cache_write_tokens,
                u.cost_usd(),
            ),
        )
    assert cur.lastrowid is not None
    return cur.lastrowid


def mark_ready(conn: sqlite3.Connection, text_id: int) -> None:
    with conn:
        conn.execute("UPDATE texts SET status = 'ready' WHERE id = ?", (text_id,))


def text_status(conn: sqlite3.Connection, text_id: int) -> str | None:
    row = conn.execute("SELECT status FROM texts WHERE id = ?", (text_id,)).fetchone()
    return row[0] if row else None


def next_ready_text(conn: sqlite3.Connection, topic_id: int) -> StoredText | None:
    row = conn.execute(
        f"SELECT {_TEXT_COLUMNS} FROM texts WHERE topic_id = ? AND status = 'ready' "
        "ORDER BY id LIMIT 1",
        (topic_id,),
    ).fetchone()
    return _text(row) if row else None


def get_text(conn: sqlite3.Connection, text_id: int) -> StoredText | None:
    row = conn.execute(f"SELECT {_TEXT_COLUMNS} FROM texts WHERE id = ?", (text_id,)).fetchone()
    return _text(row) if row else None


_TEXT_COLUMNS = "id, topic_id, title, lines, glosses, stretch, coverage"


def _text(row: tuple[Any, ...]) -> StoredText:
    text_id, topic_id, title, lines, glosses, stretch, coverage = row
    return StoredText(
        id=text_id,
        topic_id=topic_id,
        title=title,
        lines=tuple(Line(**ln) for ln in json.loads(lines)),
        glosses=json.loads(glosses),
        stretch=tuple(json.loads(stretch)),
        coverage=coverage,
    )


# ==== Readings ====


def log_reading(conn: sqlite3.Connection, text_id: int, reading: Reading, now: datetime) -> None:
    """Records one session with a text. The text leaves the ready queue either way, so the same
    text isn't served twice."""
    with conn:
        conn.execute(
            """INSERT INTO readings (text_id, logged_at, language, mode, rating, finished,
                   words_glossed, words_flagged, audio_speed, listen_only, seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                text_id,
                now.isoformat(),
                LANGUAGE,
                MODE,
                reading.rating,
                int(reading.finished),
                json.dumps(list(reading.words_glossed), ensure_ascii=False),
                json.dumps(list(reading.words_flagged), ensure_ascii=False),
                reading.audio_speed,
                int(reading.listen_only),
                reading.seconds,
            ),
        )
        conn.execute("UPDATE texts SET status = 'read' WHERE id = ?", (text_id,))


# ==== Difficulty ====


def load_difficulty(conn: sqlite3.Connection) -> Difficulty:
    raw = _get_meta(conn, "difficulty")
    return Difficulty(**json.loads(raw)) if raw else Difficulty()


def save_difficulty(conn: sqlite3.Connection, difficulty: Difficulty) -> None:
    with conn:
        _set_meta(conn, "difficulty", json.dumps(difficulty.__dict__))


def _get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
