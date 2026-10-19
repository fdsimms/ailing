import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from scripted import BAD, ENTRIES, GOOD, ScriptedModel

from ailing import store
from ailing.difficulty import Difficulty
from ailing.engine import FAILURE_COOLDOWN, MISSED_FLOOR, Engine, NotAvailable, NotFound
from ailing.generator import GenerationFailed
from ailing.store import Reading, StoredText

NOW = datetime(2026, 10, 19, 9, 0)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def engine(
    model: ScriptedModel | None, with_lexicon: bool = True, clock: Clock | None = None
) -> Engine:
    conn = store.connect(":memory:")
    if with_lexicon:
        store.save_snapshot(conn, ENTRIES, NOW)
    return Engine(conn, model.ask_for if model else None, None, clock or Clock(), random.Random(1))


def run(scenario: Callable[[], Awaitable[Any]]) -> Any:
    return asyncio.run(scenario())  # type: ignore[arg-type]


async def settle(e: Engine) -> None:
    """Lets every background write finish."""
    while e._tasks:
        await asyncio.gather(*list(e._tasks))


async def fetch(e: Engine, topic_id: int) -> StoredText:
    """What the app does: ask, and ask again once a background write has finished."""
    for _ in range(5):
        text = await e.next_text(topic_id)
        if text is not None:
            return text
        await settle(e)
    raise AssertionError("no text")


def reading(rating: str | None) -> Reading:
    return Reading(rating, True, (), (), 1.0, False, 120)


def test_asking_for_a_topic_with_nothing_ready_writes_one_in_the_background() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    async def scenario() -> tuple[StoredText | None, str, StoredText]:
        first = await e.next_text(topic.id)
        state = e.topic_state(store.get_topic(e.conn, topic.id))  # type: ignore[arg-type]
        return first, state, await fetch(e, topic.id)

    first, state, text = run(scenario)

    assert first is None
    assert state == "writing"
    assert text.title == "At the stall"
    assert text.stretch == ("ข้าวเหนียวมะม่วง",)
    assert model.calls == 1


def test_asking_again_while_writing_does_not_start_a_second_write() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    async def scenario() -> None:
        assert await e.next_text(topic.id) is None
        assert await e.next_text(topic.id) is None
        await settle(e)

    run(scenario)
    assert model.calls == 1
    assert store.get_topic(e.conn, topic.id).ready == 1  # type: ignore[union-attr]


def test_a_caller_waiting_on_the_lock_takes_the_text_just_written() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    async def scenario() -> tuple[StoredText | None, StoredText | None]:
        a, b = await asyncio.gather(e.make_text(topic.id), e.make_text(topic.id))
        return a, b

    a, b = run(scenario)
    assert a is not None and b is not None and a.id == b.id
    assert model.calls == 1


def test_a_ready_text_is_served_without_calling_the_model() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    made = run(lambda: e.make_text(topic.id))

    served = run(lambda: e.next_text(topic.id))

    assert served is not None and served.id == made.id
    assert model.calls == 1


def test_a_text_that_misses_the_floor_is_reported_once_then_retried() -> None:
    model = ScriptedModel(BAD)
    e = engine(model)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    async def scenario() -> None:
        assert await e.next_text(topic.id) is None
        await settle(e)
        with pytest.raises(NotAvailable, match="Couldn't write a text that fits"):
            await e.next_text(topic.id)
        assert e.topic_state(store.get_topic(e.conn, topic.id)) == "failed"  # type: ignore[arg-type]
        assert await e.next_text(topic.id) is None  # asking again is a deliberate retry
        await settle(e)

    run(scenario)
    assert store.get_topic(e.conn, topic.id).ready == 0  # type: ignore[union-attr]
    assert model.calls == 6


def test_a_dropped_text_is_kept_for_its_cost_but_never_served() -> None:
    e = engine(ScriptedModel(BAD))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    assert run(lambda: e.make_text(topic.id)) is None
    rows = e.conn.execute("SELECT status, cost_usd FROM texts").fetchall()
    assert len(rows) == 1 and rows[0][0] == "dropped" and rows[0][1] > 0
    assert store.next_ready_text(e.conn, topic.id) is None


def test_a_claude_error_is_reported_to_the_next_request() -> None:
    e = engine(ScriptedModel(GOOD))

    def failing(entries: Any) -> Any:
        async def ask(messages: Any) -> Any:
            raise GenerationFailed("Claude didn't answer (APIConnectionError)")

        return ask

    e.ask_for = failing
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    async def scenario() -> None:
        await e.next_text(topic.id)
        await settle(e)
        with pytest.raises(NotAvailable, match="APIConnectionError"):
            await e.next_text(topic.id)

    run(scenario)


def test_says_what_is_missing() -> None:
    no_key = engine(None)
    topic = store.add_topic(no_key.conn, "Food stall", True, NOW)
    with pytest.raises(NotAvailable, match="no Claude API key"):
        run(lambda: no_key.next_text(topic.id))

    no_words = engine(ScriptedModel(GOOD), with_lexicon=False)
    topic = store.add_topic(no_words.conn, "Food stall", True, NOW)
    with pytest.raises(NotAvailable, match="no word list"):
        run(lambda: no_words.next_text(topic.id))


def test_an_unknown_topic_is_not_found() -> None:
    with pytest.raises(NotFound):
        run(lambda: engine(ScriptedModel(GOOD)).next_text(99))


def test_top_up_fills_each_favorite_once_and_skips_others() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    store.add_topic(e.conn, "Food stall", True, NOW)
    store.add_topic(e.conn, "Taxi", True, NOW)
    store.add_topic(e.conn, "Weather", False, NOW)

    run(e.top_up)
    run(e.top_up)

    ready = {t.name: t.ready for t in store.list_topics(e.conn)}
    assert ready == {"Food stall": 1, "Taxi": 1, "Weather": 0}
    assert model.calls == 2


def test_top_up_carries_on_past_a_failed_topic_and_cools_it_down() -> None:
    clock = Clock()
    # The first topic in name order misses three times; the second gets a good text.
    model = ScriptedModel(BAD, BAD, BAD, GOOD)
    e = engine(model, clock=clock)
    store.add_topic(e.conn, "At the market", True, NOW)
    store.add_topic(e.conn, "Taxi", True, NOW)

    run(e.top_up)
    assert {t.name: e.topic_state(t) for t in store.list_topics(e.conn)} == {
        "At the market": "failed",
        "Taxi": "ready",
    }

    run(e.top_up)  # still cooling down: no new attempt
    assert model.calls == 4

    clock.now = NOW + FAILURE_COOLDOWN
    run(e.top_up)
    assert model.calls == 5


def test_top_up_stops_quietly_without_a_key() -> None:
    e = engine(None)
    store.add_topic(e.conn, "Food stall", True, NOW)
    run(e.top_up)  # no exception
    assert e.topic_state(store.list_topics(e.conn)[0]) == "idle"


def test_the_difficulty_follows_the_rating() -> None:
    e = engine(ScriptedModel(GOOD))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    text = run(lambda: fetch(e, topic.id))

    e.record_reading(text.id, reading("too_hard"))

    assert store.load_difficulty(e.conn) == Difficulty(0.96, 1)
    assert store.get_topic(e.conn, topic.id).ready == 0  # type: ignore[union-attr]


def test_a_repeated_reading_is_ignored() -> None:
    e = engine(ScriptedModel(GOOD))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    text = run(lambda: fetch(e, topic.id))

    e.record_reading(text.id, reading("too_hard"))
    e.record_reading(text.id, reading("too_hard"))

    assert store.load_difficulty(e.conn) == Difficulty(0.96, 1)
    assert e.conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 1


def test_a_reading_without_a_rating_leaves_difficulty_alone() -> None:
    e = engine(ScriptedModel(GOOD))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    text = run(lambda: fetch(e, topic.id))
    e.record_reading(text.id, reading(None))
    assert store.load_difficulty(e.conn) == Difficulty()


def test_reading_an_unknown_text_is_not_found() -> None:
    with pytest.raises(NotFound):
        engine(ScriptedModel(GOOD)).record_reading(42, reading(None))


def test_the_missed_floor_message_is_plain() -> None:
    assert "Try again or pick another topic" in MISSED_FLOOR


class FakeVoice:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_on = fail_on

    async def __call__(self, text: str, voice: str) -> bytes:
        from ailing.tts import TtsFailed

        self.calls.append((text, voice))
        if text == self.fail_on:
            raise TtsFailed("Azure answered 500")
        return f"mp3:{text}".encode()


def speaking_engine(tmp_path: Path, voice: FakeVoice | None) -> Engine:
    from ailing.tts import AudioCache

    conn = store.connect(":memory:")
    store.save_snapshot(conn, ENTRIES, NOW)
    return Engine(
        conn,
        ScriptedModel(GOOD).ask_for,
        None,
        Clock(),
        random.Random(1),
        synthesize=voice,
        audio=AudioCache(tmp_path),
        voices={"A": "voice-a", "B": "voice-b"},
    )


def test_a_new_text_gets_audio_for_each_line_in_its_speakers_voice(tmp_path: Path) -> None:
    voice = FakeVoice()
    e = speaking_engine(tmp_path, voice)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    text = run(lambda: fetch(e, topic.id))

    assert voice.calls == [
        ("ฉันอยากกินข้าวเหนียวมะม่วงครับ", "voice-a"),
        ("ข้าวเหนียวมะม่วงครับ!", "voice-b"),
    ]
    assert e.has_audio(text.id, 0) and e.has_audio(text.id, 1)


def test_a_text_is_not_ready_until_its_audio_is_made(tmp_path: Path) -> None:
    seen: list[str | None] = []
    e = speaking_engine(tmp_path, None)

    async def voice(text: str, name: str) -> bytes:
        seen.append(store.text_status(e.conn, 1))
        return b"mp3"

    e.synthesize = voice
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    run(lambda: e.make_text(topic.id))

    assert seen == ["pending", "pending"]
    assert store.text_status(e.conn, 1) == "ready"


def test_a_pending_text_left_by_a_restart_becomes_ready(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    e = engine(ScriptedModel(GOOD))
    e.conn = store.connect(db)
    store.save_snapshot(e.conn, ENTRIES, NOW)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    run(lambda: e.make_text(topic.id))
    e.conn.execute("UPDATE texts SET status = 'pending'")
    e.conn.commit()

    assert store.text_status(store.connect(db), 1) == "ready"


def test_a_failed_line_stays_silent_and_the_text_is_still_served(tmp_path: Path) -> None:
    e = speaking_engine(tmp_path, FakeVoice(fail_on="ข้าวเหนียวมะม่วงครับ!"))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    text = run(lambda: fetch(e, topic.id))

    assert e.has_audio(text.id, 0)
    assert not e.has_audio(text.id, 1)


def test_missing_audio_is_made_on_request_and_then_cached(tmp_path: Path) -> None:
    e = speaking_engine(tmp_path, None)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    text = run(lambda: fetch(e, topic.id))
    assert run(lambda: e.line_audio(text, 0)) is None  # no text to speech yet

    voice = FakeVoice()
    e.synthesize = voice
    path = run(lambda: e.line_audio(text, 0))
    again = run(lambda: e.line_audio(text, 0))

    assert path is not None and path.read_bytes().startswith(b"mp3:")
    assert again == path
    assert len(voice.calls) == 1
    assert run(lambda: e.line_audio(text, 9)) is None


# ==== Stretch words setting ====


def test_by_default_the_model_chooses_stretch_words_from_a_list() -> None:
    e = engine(ScriptedModel(GOOD))
    store.save_difficulty(e.conn, Difficulty(stretch=1))
    request = e._request("Food stall", ENTRIES, store.load_difficulty(e.conn))
    assert request.choose == 1
    # Due and young words only; the deck here has just the one.
    assert [w.text for w in request.stretch] == ["ข้าวเหนียวมะม่วง"]


def test_set_to_any_the_stretch_words_are_given() -> None:
    e = engine(ScriptedModel(GOOD))
    store.save_settings(e.conn, store.Settings(stretch_words="any"))
    request = e._request("Food stall", ENTRIES, Difficulty(stretch=2))
    assert request.choose is None
    assert [w.text for w in request.stretch] == ["ข้าวเหนียวมะม่วง"]


def test_a_text_records_the_stretch_words_the_model_chose() -> None:
    e = engine(ScriptedModel(GOOD))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    text = run(lambda: fetch(e, topic.id))
    assert text.stretch == ("ข้าวเหนียวมะม่วง",)
