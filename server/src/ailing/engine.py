"""What the API does, apart from HTTP: serve a ready text, make one when none is ready, keep each
favorite topic's queue topped up, and log readings (docs/architecture.md, Hosting and Topics).

Everything outside the process is injected: the model (`ask_for`), Anki (`call_tool`), the clock
and the random source. Either outside service can be missing, and the engine says which.
"""

import asyncio
import logging
import random
import sqlite3
from collections.abc import Callable
from datetime import datetime

from ailing import store
from ailing.coverage import Lexicon
from ailing.difficulty import adapt
from ailing.gateway import CallTool
from ailing.generator import Ask, GenerationFailed, TextRequest, generate
from ailing.lexicon import Entry, lexicon_from
from ailing.store import Reading, StoredText
from ailing.stretch import pick_stretch

READY_PER_FAVORITE = 1

log = logging.getLogger(__name__)


class NotAvailable(Exception):
    """Something the request needs isn't set up yet. The message says what, for the app to show."""


class Engine:
    def __init__(
        self,
        conn: sqlite3.Connection,
        ask_for: Callable[[list[Entry]], Ask] | None,
        call_tool: CallTool | None,
        clock: Callable[[], datetime] = datetime.now,
        rng: random.Random | None = None,
    ) -> None:
        self.conn = conn
        self.ask_for = ask_for
        self.call_tool = call_tool
        self.clock = clock
        self.rng = rng or random.Random()
        self._topic_locks: dict[int, asyncio.Lock] = {}
        self._topping_up = asyncio.Lock()

    def snapshot(self) -> tuple[list[Entry], Lexicon]:
        """The current entries and their lexicon (cached by `lexicon_from`)."""
        entries = store.load_snapshot(self.conn)[0]
        return entries, lexicon_from(entries)

    def entries(self) -> list[Entry]:
        return self.snapshot()[0]

    async def refresh_lexicon(self) -> None:
        if self.call_tool is not None:
            await store.refresh_if_stale(self.conn, self.call_tool, self.clock())

    async def next_text(self, topic_id: int) -> StoredText:
        if store.get_topic(self.conn, topic_id) is None:
            raise KeyError(topic_id)
        ready = store.next_ready_text(self.conn, topic_id)
        if ready is not None:
            return ready
        text = await self.make_text(topic_id)
        if text is None:
            raise NotAvailable(
                "Couldn't write a text that fits your words this time. Try again or pick another "
                "topic."
            )
        return text

    async def make_text(self, topic_id: int) -> StoredText | None:
        """Generates and stores one text, or returns None when three attempts all missed the
        coverage floor. One generation per topic at a time."""
        lock = self._topic_locks.setdefault(topic_id, asyncio.Lock())
        async with lock:
            topic = store.get_topic(self.conn, topic_id)
            assert topic is not None
            if self.ask_for is None:
                raise NotAvailable("The server has no Claude API key yet.")
            entries, lexicon = self.snapshot()
            if not entries:
                raise NotAvailable("The server has no word list from Anki yet.")
            difficulty = store.load_difficulty(self.conn)
            stretch = pick_stretch(entries, difficulty.stretch, self.rng)
            request = TextRequest(topic.name, tuple(stretch), floor=difficulty.floor)
            result = await generate(self.ask_for(entries), lexicon, request)
            if not result.passed:
                log.warning(
                    "Dropped a %r text at %.1f%% after %d attempts ($%.4f)",
                    topic.name,
                    result.coverage.ratio * 100,
                    result.attempts,
                    result.usage.cost_usd(),
                )
                return None
            text_id = store.save_text(
                self.conn,
                topic_id,
                result,
                [e.text for e in stretch],
                difficulty.floor,
                self.clock(),
            )
            return store.get_text(self.conn, text_id)

    async def top_up(self) -> None:
        """Refreshes the lexicon if it's a day old, then makes sure each favorite topic has a ready
        text. Runs after a response is sent; a second call while one is running does nothing."""
        if self._topping_up.locked():
            return
        async with self._topping_up:
            await self.refresh_lexicon()
            for topic in store.list_topics(self.conn):
                if not topic.favorite or topic.ready >= READY_PER_FAVORITE:
                    continue
                try:
                    await self.make_text(topic.id)
                except (NotAvailable, GenerationFailed) as e:
                    log.warning("Couldn't top up %r: %s", topic.name, e)
                    return

    def record_reading(self, text_id: int, reading: Reading) -> None:
        if store.get_text(self.conn, text_id) is None:
            raise KeyError(text_id)
        store.log_reading(self.conn, text_id, reading, self.clock())
        if reading.rating is not None:
            current = store.load_difficulty(self.conn)
            store.save_difficulty(self.conn, adapt(current, reading.rating))
