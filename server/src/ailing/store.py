"""SQLite storage: the lexicon snapshot, topics, generated texts, the reading log, the difficulty
setting and the owner's settings. Only the latest lexicon snapshot is kept (docs/architecture.md, Lexicon)."""

import json
import logging
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from ailing.difficulty import Difficulty
from ailing.gateway import AnkiUnavailable, CallTool
from ailing.generator import MODEL, Form, Generated, Line
from ailing.languages import LANGUAGES, Code
from ailing.lexicon import Entry, fetch_snapshot

SNAPSHOT_MAX_AGE = timedelta(hours=24)
# How the reading log names each language (it said "thai" before there was a second one).
LOG_LANGUAGE: dict[Code, str] = {"th": "thai", "es": "spanish"}
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
CREATE TABLE IF NOT EXISTS cleared_words (
    word TEXT PRIMARY KEY,
    cleared_at TEXT NOT NULL
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
    roles: dict[str, str] = field(default_factory=dict)
    form: Form = "dialogue"
    language: Code = "th"


# "topic": the model chooses stretch words that fit the topic from a list of due and young words.
# "any": the stretch words are picked at random from that list and the model has to use them.
StretchWords = Literal["topic", "any"]


# How many lines a dialogue has: short, medium or long.
Length = Literal[6, 8, 12]


@dataclass(frozen=True)
class Settings:
    stretch_words: StretchWords = "topic"
    lines: Length = 8
    form: Form = "dialogue"
    language: Code = "th"  # the language new texts are written and served in


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
    if "roles" not in {r[1] for r in conn.execute("PRAGMA table_info(texts)")}:
        # Texts written before speakers had roles have none, and show only A and B.
        conn.execute("ALTER TABLE texts ADD COLUMN roles TEXT NOT NULL DEFAULT '{}'")
    for table in ("lexicon", "texts"):
        if "language" not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            # Everything from before Spanish is Thai.
            conn.execute(f"ALTER TABLE {table} ADD COLUMN language TEXT NOT NULL DEFAULT 'th'")
    if "form" not in {r[1] for r in conn.execute("PRAGMA table_info(texts)")}:
        # Every text written before stories was a dialogue.
        conn.execute("ALTER TABLE texts ADD COLUMN form TEXT NOT NULL DEFAULT 'dialogue'")
    if "removed" not in {r[1] for r in conn.execute("PRAGMA table_info(topics)")}:
        # A removed topic is hidden, not deleted, since its texts and readings point at it.
        conn.execute("ALTER TABLE topics ADD COLUMN removed INTEGER NOT NULL DEFAULT 0")
    with conn:
        # A text left pending by a restart mid-audio: its missing lines are made on request.
        conn.execute("UPDATE texts SET status = 'ready' WHERE status = 'pending'")
    return conn


# ==== Lexicon ====


def _per_language(key: str, language: Code) -> str:
    # Thai keeps the key it had before there was a second language.
    return key if language == "th" else f"{key}:{language}"


def save_snapshot(
    conn: sqlite3.Connection, entries: list[Entry], taken_at: datetime, language: Code = "th"
) -> None:
    """Replaces one language's whole snapshot in one transaction, so a reader never sees half."""
    with conn:
        conn.execute("DELETE FROM lexicon WHERE language = ?", (language,))
        conn.executemany(
            # OR REPLACE: a note moved to the other language's deck belongs to the newer snapshot.
            "INSERT OR REPLACE INTO lexicon (note_id, entry, meaning, tier, due, language)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(e.note_id, e.text, e.meaning, e.tier, int(e.due), language) for e in entries],
        )
        _set_meta(conn, _per_language("snapshot_taken_at", language), taken_at.isoformat())


def load_snapshot(
    conn: sqlite3.Connection, language: Code = "th"
) -> tuple[list[Entry], datetime | None]:
    rows = conn.execute(
        "SELECT note_id, entry, meaning, tier, due FROM lexicon WHERE language = ?"
        " ORDER BY note_id",
        (language,),
    )
    entries = [
        Entry(nid, entry, meaning, tier, bool(due)) for nid, entry, meaning, tier, due in rows
    ]
    taken_at = _get_meta(conn, _per_language("snapshot_taken_at", language))
    return entries, datetime.fromisoformat(taken_at) if taken_at else None


def is_stale(taken_at: datetime | None, now: datetime) -> bool:
    return taken_at is None or now - taken_at >= SNAPSHOT_MAX_AGE


async def refresh_if_stale(
    conn: sqlite3.Connection, call: CallTool, now: datetime, language: Code = "th"
) -> bool:
    """Takes a new snapshot of one language's deck when the last one is a day old. If Anki can't
    be reached, the old snapshot stays in place and the app keeps running on it. Returns whether
    it refreshed."""
    _, taken_at = load_snapshot(conn, language)
    if not is_stale(taken_at, now):
        return False
    name = LANGUAGES[language].name
    try:
        entries = await fetch_snapshot(call, LANGUAGES[language])
    except AnkiUnavailable as e:
        log.warning("%s lexicon not refreshed, using the snapshot from %s: %s", name, taken_at, e)
        return False
    if not entries:
        log.warning("Anki returned no %s notes; keeping the snapshot from %s", name, taken_at)
        return False
    save_snapshot(conn, entries, now, language)
    return True


# ==== Topics ====


def add_topic(conn: sqlite3.Connection, name: str, favorite: bool, now: datetime) -> Topic:
    """Adds a topic, or returns the existing one with that name (ignoring case). A removed topic
    with that name comes back, with any text it still had ready."""
    name = " ".join(name.split())
    if not name:
        raise ValueError("A topic needs a name")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO topics (name, favorite, created_at) VALUES (?, ?, ?)",
            (name, int(favorite), now.isoformat()),
        )
        conn.execute(
            "UPDATE topics SET removed = 0, favorite = ? WHERE name = ? AND removed = 1",
            (int(favorite), name),
        )
    row = conn.execute("SELECT id FROM topics WHERE name = ?", (name,)).fetchone()
    topic = get_topic(conn, row[0])
    assert topic is not None
    return topic


def get_topic(conn: sqlite3.Connection, topic_id: int, language: Code = "th") -> Topic | None:
    return next((t for t in list_topics(conn, language) if t.id == topic_id), None)


def list_topics(conn: sqlite3.Connection, language: Code = "th") -> list[Topic]:
    """Topics are shared by every language; `ready` counts the texts waiting in this one."""
    rows = conn.execute(
        """SELECT t.id, t.name, t.favorite,
                  (SELECT COUNT(*) FROM texts x WHERE x.topic_id = t.id AND x.status = 'ready'
                   AND x.language = ?)
           FROM topics t WHERE t.removed = 0 ORDER BY t.favorite DESC, t.name""",
        (language,),
    )
    return [Topic(i, name, bool(fav), ready) for i, name, fav, ready in rows]


def set_favorite(conn: sqlite3.Connection, topic_id: int, favorite: bool) -> Topic | None:
    with conn:
        conn.execute(
            "UPDATE topics SET favorite = ? WHERE id = ? AND removed = 0", (int(favorite), topic_id)
        )
    return get_topic(conn, topic_id)


def topic_names(conn: sqlite3.Connection) -> set[str]:
    """Every topic's name, removed ones included."""
    return {name for (name,) in conn.execute("SELECT name FROM topics")}


def remove_topic(conn: sqlite3.Connection, topic_id: int) -> bool:
    """Hides a topic from the list and the background top-up. Returns whether there was one."""
    with conn:
        cur = conn.execute(
            "UPDATE topics SET removed = 1 WHERE id = ? AND removed = 0", (topic_id,)
        )
    return cur.rowcount > 0


# ==== Texts ====


def save_text(
    conn: sqlite3.Connection,
    topic_id: int,
    generated: Generated,
    stretch: list[str],
    floor: float,
    now: datetime,
    status: str = "ready",
    form: Form = "dialogue",
    language: Code = "th",
) -> int:
    """Stores a generated text. `status` is "pending" while its audio is made, "ready" once it can
    be served, or "dropped" for a text that missed the floor (kept only for its cost)."""
    u = generated.usage
    with conn:
        cur = conn.execute(
            """INSERT INTO texts (topic_id, created_at, status, title, lines, glosses, stretch,
                   coverage, token_count, floor, attempts, model, input_tokens, output_tokens,
                   cache_read_tokens, cache_write_tokens, cost_usd, roles, form, language)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                json.dumps(generated.roles, ensure_ascii=False),
                form,
                language,
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


def next_ready_text(
    conn: sqlite3.Connection, topic_id: int, language: Code = "th"
) -> StoredText | None:
    row = conn.execute(
        f"SELECT {_TEXT_COLUMNS} FROM texts WHERE topic_id = ? AND status = 'ready' "
        "AND language = ? ORDER BY id LIMIT 1",
        (topic_id, language),
    ).fetchone()
    return _text(row) if row else None


def get_text(conn: sqlite3.Connection, text_id: int) -> StoredText | None:
    row = conn.execute(f"SELECT {_TEXT_COLUMNS} FROM texts WHERE id = ?", (text_id,)).fetchone()
    return _text(row) if row else None


_TEXT_COLUMNS = "id, topic_id, title, lines, glosses, stretch, coverage, roles, form, language"


def _text(row: tuple[Any, ...]) -> StoredText:
    text_id, topic_id, title, lines, glosses, stretch, coverage, roles, form, language = row
    return StoredText(
        id=text_id,
        topic_id=topic_id,
        title=title,
        lines=tuple(Line(**ln) for ln in json.loads(lines)),
        glosses=json.loads(glosses),
        stretch=tuple(json.loads(stretch)),
        coverage=coverage,
        roles=json.loads(roles),
        form=form,
        language=language,
    )


# ==== Readings ====


def log_reading(conn: sqlite3.Connection, text_id: int, reading: Reading, now: datetime) -> None:
    """Records one session with a text. The text leaves the ready queue either way, so the same
    text isn't served twice."""
    row = conn.execute("SELECT language FROM texts WHERE id = ?", (text_id,)).fetchone()
    language: Code = row[0] if row else "th"
    with conn:
        conn.execute(
            """INSERT INTO readings (text_id, logged_at, language, mode, rating, finished,
                   words_glossed, words_flagged, audio_speed, listen_only, seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                text_id,
                now.isoformat(),
                LOG_LANGUAGE[language],
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


@dataclass(frozen=True)
class Progress:
    """Finished readings since a date: what the Milestone 1 exit check reads (docs/brief.md)."""

    finished: int
    median_coverage: float | None
    ratings: dict[str, int]  # too_easy, about_right, too_hard, and none for unrated


def progress(conn: sqlite3.Connection, since: datetime, language: Code = "th") -> Progress:
    rows = conn.execute(
        """SELECT x.coverage, r.rating FROM readings r JOIN texts x ON x.id = r.text_id
           WHERE r.finished = 1 AND r.logged_at >= ? AND x.language = ?""",
        (since.isoformat(), language),
    ).fetchall()
    ratings = {"too_easy": 0, "about_right": 0, "too_hard": 0, "none": 0}
    for _, rating in rows:
        ratings[rating or "none"] += 1
    coverages = [coverage for coverage, _ in rows]
    median = statistics.median(coverages) if coverages else None
    return Progress(len(rows), median, ratings)


def practiced_days(
    conn: sqlite3.Connection, before: datetime, language: Code = "th"
) -> dict[str, int]:
    """For each word that was a stretch word in a text read before `before`, the number of
    different days it was one."""
    rows = conn.execute(
        """SELECT DISTINCT substr(r.logged_at, 1, 10), x.stretch FROM readings r
           JOIN texts x ON x.id = r.text_id WHERE r.logged_at < ? AND x.language = ?""",
        (before.isoformat(), language),
    )
    days: dict[str, set[str]] = {}
    for day, stretch in rows:
        for word in json.loads(stretch):
            days.setdefault(word, set()).add(day)
    return {word: len(d) for word, d in days.items()}


@dataclass(frozen=True)
class PastText:
    id: int
    topic: str
    title: str
    rating: str | None
    read_at: datetime
    coverage: float
    form: Form = "dialogue"


def past_texts(conn: sqlite3.Connection, limit: int, language: Code = "th") -> list[PastText]:
    """Texts in this language read to the end, most recent first."""
    rows = conn.execute(
        """SELECT x.id, t.name, x.title, r.rating, r.logged_at, x.coverage, x.form FROM readings r
           JOIN texts x ON x.id = r.text_id JOIN topics t ON t.id = x.topic_id
           WHERE r.finished = 1 AND x.language = ? ORDER BY r.id DESC LIMIT ?""",
        (language, limit),
    )
    return [
        PastText(i, topic, title, rating, datetime.fromisoformat(at), coverage, form)
        for i, topic, title, rating, at, coverage, form in rows
    ]


# ==== Marked words ====


@dataclass(frozen=True)
class MarkedWord:
    word: str
    times: int  # readings it was marked in since it was last cleared
    last_marked: datetime
    glosses: dict[str, str]  # the glosses of the last text it was marked in


def marked_words(conn: sqlite3.Connection, language: Code = "th") -> list[MarkedWord]:
    """Every word marked unknown in a reading in this language and not cleared since, most
    recently marked first."""
    cleared = {
        word: datetime.fromisoformat(at)
        for word, at in conn.execute("SELECT word, cleared_at FROM cleared_words")
    }
    rows = conn.execute(
        """SELECT r.logged_at, r.words_flagged, x.glosses FROM readings r
           JOIN texts x ON x.id = r.text_id WHERE x.language = ? ORDER BY r.id""",
        (language,),
    )
    found: dict[str, MarkedWord] = {}
    for logged_at, flagged, glosses in rows:
        at = datetime.fromisoformat(logged_at)
        for word in json.loads(flagged):
            if word in cleared and at <= cleared[word]:
                continue
            times = found[word].times + 1 if word in found else 1
            found[word] = MarkedWord(word, times, at, json.loads(glosses))
    return sorted(found.values(), key=lambda w: w.last_marked, reverse=True)


def clear_word(conn: sqlite3.Connection, word: str, now: datetime) -> None:
    """Takes a word off the marked list until it's marked again."""
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO cleared_words (word, cleared_at) VALUES (?, ?)",
            (word, now.isoformat()),
        )


# ==== Difficulty ====


def load_difficulty(conn: sqlite3.Connection, language: Code = "th") -> Difficulty:
    """Each language has its own, moved by ratings of texts in that language."""
    raw = _get_meta(conn, _per_language("difficulty", language))
    return Difficulty(**json.loads(raw)) if raw else Difficulty()


def save_difficulty(
    conn: sqlite3.Connection, difficulty: Difficulty, language: Code = "th"
) -> None:
    with conn:
        _set_meta(conn, _per_language("difficulty", language), json.dumps(difficulty.__dict__))


# ==== Settings ====


def load_settings(conn: sqlite3.Connection) -> Settings:
    raw = _get_meta(conn, "settings")
    saved = json.loads(raw) if raw else {}
    # Only known keys, so a setting removed later doesn't break loading.
    return Settings(**{k: v for k, v in saved.items() if k in Settings.__dataclass_fields__})


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    with conn:
        _set_meta(conn, "settings", json.dumps(settings.__dict__))


def _get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
