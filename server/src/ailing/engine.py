"""What the API does, apart from HTTP: serve a ready text, write one in the background when none is
ready, keep each favorite topic's queue topped up, and log readings (docs/architecture.md, Hosting
and Topics).

Writing a text takes up to a minute or more (three attempts, then audio), longer than an iPhone
waits on one request, so `/next` never waits for it: `next_text` returns a ready text or starts a
background write and returns None, and the app asks again. A write that fails is reported to the
next request for that topic, once, and keeps the background top-up off that topic for
`FAILURE_COOLDOWN`, so a topic that keeps missing the floor doesn't keep spending.

Everything outside the process is injected: the model (`ask_for`), Anki (`call_tool`), text to
speech, the clock and the random source. Any of them can be missing, and the engine says which.
"""

import asyncio
import logging
import random
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from ailing import store
from ailing.coverage import Lexicon, parse_line
from ailing.difficulty import Difficulty, adapt
from ailing.gateway import CallTool
from ailing.generator import Ask, GenerationFailed, TextRequest, generate
from ailing.lexicon import Entry, lexicon_from
from ailing.store import Reading, StoredText, Topic
from ailing.stretch import pick_stretch
from ailing.tts import DEFAULT_VOICES, AudioCache, Synthesize, TtsFailed

READY_PER_FAVORITE = 1
# How many due or young words the model chooses its stretch words from, when it's choosing.
STRETCH_CHOICES = 15
FAILURE_COOLDOWN = timedelta(minutes=30)
MISSED_FLOOR = (
    "Couldn't write a text that fits your words this time. Try again or pick another topic."
)

TopicState = Literal["ready", "writing", "failed", "idle"]

log = logging.getLogger(__name__)


class NotAvailable(Exception):
    """Something the request needs isn't set up yet, or the last write for this topic failed. The
    message says what, for the app to show."""


class NotFound(Exception):
    """No topic or text with that id."""


@dataclass
class _Failure:
    at: datetime
    message: str
    reported: bool = False


class Engine:
    def __init__(
        self,
        conn: sqlite3.Connection,
        ask_for: Callable[[list[Entry]], Ask] | None,
        call_tool: CallTool | None,
        clock: Callable[[], datetime] = datetime.now,
        rng: random.Random | None = None,
        synthesize: Synthesize | None = None,
        audio: AudioCache | None = None,
        voices: dict[str, str] | None = None,
    ) -> None:
        self.conn = conn
        self.ask_for = ask_for
        self.call_tool = call_tool
        self.clock = clock
        self.rng = rng or random.Random()
        self.synthesize = synthesize
        self.audio = audio
        self.voices = voices or DEFAULT_VOICES
        self._topic_locks: dict[int, asyncio.Lock] = {}
        self._topping_up = asyncio.Lock()
        self._writing: set[int] = set()
        self._failures: dict[int, _Failure] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # ==== Lexicon ====

    def snapshot(self) -> tuple[list[Entry], Lexicon]:
        """The current entries and their lexicon (cached by `lexicon_from`)."""
        entries = store.load_snapshot(self.conn)[0]
        return entries, lexicon_from(entries)

    def entries(self) -> list[Entry]:
        return self.snapshot()[0]

    async def refresh_lexicon(self) -> None:
        if self.call_tool is not None:
            await store.refresh_if_stale(self.conn, self.call_tool, self.clock())

    # ==== Serving ====

    def topic_state(self, topic: Topic) -> TopicState:
        if topic.ready > 0:
            return "ready"
        if topic.id in self._writing:
            return "writing"
        if self._cooling_down(topic.id):
            return "failed"
        return "idle"

    async def next_text(self, topic_id: int) -> StoredText | None:
        """A ready text, or None while one is being written in the background (started here if
        nothing is writing). A failed write is raised once as NotAvailable; asking again after that
        is a deliberate retry and starts a new write."""
        if store.get_topic(self.conn, topic_id) is None:
            raise NotFound(topic_id)
        ready = store.next_ready_text(self.conn, topic_id)
        if ready is not None:
            return ready
        if topic_id in self._writing:
            return None
        failure = self._failures.get(topic_id)
        if failure is not None and not failure.reported:
            failure.reported = True
            raise NotAvailable(failure.message)
        self._check_setup()
        self._failures.pop(topic_id, None)
        self._start(topic_id)
        return None

    def _check_setup(self) -> None:
        if self.ask_for is None:
            raise NotAvailable("The server has no Claude API key yet.")
        if not store.load_snapshot(self.conn)[0]:
            raise NotAvailable("The server has no word list from Anki yet.")

    def _start(self, topic_id: int) -> None:
        self._writing.add(topic_id)  # before the task runs, so a second request sees it
        task = asyncio.create_task(self._write(topic_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _write(self, topic_id: int) -> None:
        """Writes one text and records how it went. Never raises: this runs unattended."""
        self._writing.add(topic_id)
        try:
            if await self.make_text(topic_id) is None:
                self._fail(topic_id, MISSED_FLOOR)
        except NotAvailable as e:
            self._fail(topic_id, str(e))
        except GenerationFailed as e:
            self._fail(topic_id, f"Couldn't write a text: {e}")
        except Exception:
            log.exception("Writing a text for topic %d failed", topic_id)
            self._fail(topic_id, "Something went wrong writing a text. Try again.")
        finally:
            self._writing.discard(topic_id)

    def _fail(self, topic_id: int, message: str) -> None:
        self._failures[topic_id] = _Failure(self.clock(), message)

    def _cooling_down(self, topic_id: int) -> bool:
        failure = self._failures.get(topic_id)
        return failure is not None and self.clock() - failure.at < FAILURE_COOLDOWN

    # ==== Writing ====

    async def make_text(self, topic_id: int) -> StoredText | None:
        """Generates and stores one text, or returns None when three attempts all missed the
        coverage floor. One generation per topic at a time; a caller that waited on the lock gets
        the text the one before it just wrote instead of writing another."""
        lock = self._topic_locks.setdefault(topic_id, asyncio.Lock())
        async with lock:
            ready = store.next_ready_text(self.conn, topic_id)
            if ready is not None:
                return ready
            topic = store.get_topic(self.conn, topic_id)
            if topic is None:
                raise NotFound(topic_id)
            self._check_setup()
            assert self.ask_for is not None
            entries, lexicon = self.snapshot()
            difficulty = store.load_difficulty(self.conn)
            request = self._request(topic.name, entries, difficulty)
            result = await generate(self.ask_for(entries), lexicon, request)
            words = list(result.stretch)
            if not result.passed:
                # Stored as dropped, never served, so its cost is still on record.
                store.save_text(
                    self.conn, topic_id, result, words, difficulty.floor, self.clock(), "dropped"
                )
                log.warning(
                    "Dropped a %r text at %.1f%% after %d attempts ($%.4f)",
                    topic.name,
                    result.coverage.ratio * 100,
                    result.attempts,
                    result.usage.cost_usd(),
                )
                return None
            # Pending until its audio is made, so a text is never served half-spoken.
            text_id = store.save_text(
                self.conn, topic_id, result, words, difficulty.floor, self.clock(), "pending"
            )
            text = store.get_text(self.conn, text_id)
            assert text is not None
            await self.make_audio(text)
            store.mark_ready(self.conn, text_id)
            return text

    def _request(self, topic: str, entries: list[Entry], difficulty: Difficulty) -> TextRequest:
        if store.load_settings(self.conn).stretch_words == "any":
            stretch = pick_stretch(entries, difficulty.stretch, self.rng)
            return TextRequest(topic, tuple(stretch), floor=difficulty.floor)
        choices = pick_stretch(entries, STRETCH_CHOICES, self.rng)
        if not choices:
            return TextRequest(topic, floor=difficulty.floor)
        return TextRequest(topic, tuple(choices), floor=difficulty.floor, choose=difficulty.stretch)

    # ==== Audio ====

    def has_audio(self, text_id: int, line: int) -> bool:
        return self.audio is not None and self.audio.has(text_id, line)

    async def make_audio(self, text: StoredText) -> None:
        """Speaks every line that has no audio yet. A failure leaves that line silent and is
        logged; it never keeps the text from being served."""
        for i in range(len(text.lines)):
            await self.line_audio(text, i)

    async def line_audio(self, text: StoredText, line: int) -> Path | None:
        """The cached MP3 for one line, made now if it's missing and text to speech is set up."""
        if self.audio is None or not 0 <= line < len(text.lines):
            return None
        if self.audio.has(text.id, line):
            return self.audio.path(text.id, line)
        if self.synthesize is None:
            return None
        spoken, _ = parse_line(text.lines[line].text)
        voice = self.voices.get(text.lines[line].speaker, self.voices["A"])
        try:
            mp3 = await self.synthesize(spoken, voice)
        except TtsFailed as e:
            log.warning("No audio for text %d line %d: %s", text.id, line, e)
            return None
        self.audio.write(text.id, line, mp3)
        return self.audio.path(text.id, line)

    # ==== Top-up and readings ====

    async def top_up(self) -> None:
        """Refreshes the lexicon if it's a day old, then makes sure each favorite topic has a ready
        text. Runs after a response is sent; a second call while one is running does nothing. A
        topic that failed recently is skipped; a missing key or word list stops the whole pass."""
        if self._topping_up.locked():
            return
        async with self._topping_up:
            await self.refresh_lexicon()
            try:
                self._check_setup()
            except NotAvailable as e:
                log.info("Not topping up: %s", e)
                return
            for topic in store.list_topics(self.conn):
                if not topic.favorite or topic.ready >= READY_PER_FAVORITE:
                    continue
                if topic.id in self._writing or self._cooling_down(topic.id):
                    continue
                await self._write(topic.id)

    def record_reading(self, text_id: int, reading: Reading) -> None:
        """Logs a session and adjusts difficulty. A second reading of a text that's already been
        read is ignored, so a retried request can't log twice or move difficulty twice."""
        status = store.text_status(self.conn, text_id)
        if status is None:
            raise NotFound(text_id)
        if status == "read":
            return
        store.log_reading(self.conn, text_id, reading, self.clock())
        if reading.rating is not None:
            current = store.load_difficulty(self.conn)
            store.save_difficulty(self.conn, adapt(current, reading.rating))
