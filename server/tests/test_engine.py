import asyncio
import random
from datetime import datetime
from pathlib import Path

import pytest
from scripted import BAD, ENTRIES, GOOD, ScriptedModel

from ailing import store
from ailing.difficulty import Difficulty
from ailing.engine import Engine, NotAvailable
from ailing.store import Reading

NOW = datetime(2026, 10, 19, 9, 0)


def engine(model: ScriptedModel | None, with_lexicon: bool = True) -> Engine:
    conn = store.connect(":memory:")
    if with_lexicon:
        store.save_snapshot(conn, ENTRIES, NOW)
    return Engine(conn, model.ask_for if model else None, None, lambda: NOW, random.Random(1))


def reading(rating: str | None) -> Reading:
    return Reading(rating, True, (), (), 1.0, False, 120)


def test_next_text_generates_when_none_is_ready_and_stores_it() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    text = asyncio.run(e.next_text(topic.id))

    assert text.title == "At the stall"
    assert text.stretch == ("ข้าวเหนียวมะม่วง",)
    assert model.calls == 1


def test_a_ready_text_is_served_without_calling_the_model() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    made = asyncio.run(e.make_text(topic.id))
    assert made is not None

    served = asyncio.run(e.next_text(topic.id))

    assert served.id == made.id
    assert model.calls == 1


def test_a_text_that_never_reaches_the_floor_is_not_stored() -> None:
    e = engine(ScriptedModel(BAD))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    with pytest.raises(NotAvailable, match="Couldn't write a text"):
        asyncio.run(e.next_text(topic.id))
    assert store.get_topic(e.conn, topic.id).ready == 0  # type: ignore[union-attr]


def test_says_what_is_missing() -> None:
    no_key = engine(None)
    topic = store.add_topic(no_key.conn, "Food stall", True, NOW)
    with pytest.raises(NotAvailable, match="no Claude API key"):
        asyncio.run(no_key.next_text(topic.id))

    no_words = engine(ScriptedModel(GOOD), with_lexicon=False)
    topic = store.add_topic(no_words.conn, "Food stall", True, NOW)
    with pytest.raises(NotAvailable, match="no word list"):
        asyncio.run(no_words.next_text(topic.id))


def test_an_unknown_topic_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        asyncio.run(engine(ScriptedModel(GOOD)).next_text(99))


def test_top_up_fills_each_favorite_once_and_skips_others() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    store.add_topic(e.conn, "Food stall", True, NOW)
    store.add_topic(e.conn, "Taxi", True, NOW)
    store.add_topic(e.conn, "Weather", False, NOW)

    asyncio.run(e.top_up())
    asyncio.run(e.top_up())

    ready = {t.name: t.ready for t in store.list_topics(e.conn)}
    assert ready == {"Food stall": 1, "Taxi": 1, "Weather": 0}
    assert model.calls == 2


def test_top_up_stops_quietly_without_a_key() -> None:
    e = engine(None)
    store.add_topic(e.conn, "Food stall", True, NOW)
    asyncio.run(e.top_up())  # no exception


def test_the_difficulty_follows_the_rating_and_shapes_the_next_request() -> None:
    model = ScriptedModel(GOOD)
    e = engine(model)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    text = asyncio.run(e.next_text(topic.id))

    e.record_reading(text.id, reading("too_hard"))

    assert store.load_difficulty(e.conn) == Difficulty(0.96, 1)
    assert store.get_topic(e.conn, topic.id).ready == 0  # type: ignore[union-attr]


def test_a_reading_without_a_rating_leaves_difficulty_alone() -> None:
    e = engine(ScriptedModel(GOOD))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    text = asyncio.run(e.next_text(topic.id))
    e.record_reading(text.id, reading(None))
    assert store.load_difficulty(e.conn) == Difficulty()


def test_reading_an_unknown_text_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        engine(ScriptedModel(GOOD)).record_reading(42, reading(None))


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
        lambda: NOW,
        random.Random(1),
        synthesize=voice,
        audio=AudioCache(tmp_path),
        voices={"A": "voice-a", "B": "voice-b"},
    )


def test_a_new_text_gets_audio_for_each_line_in_its_speakers_voice(tmp_path: Path) -> None:
    voice = FakeVoice()
    e = speaking_engine(tmp_path, voice)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    text = asyncio.run(e.next_text(topic.id))

    assert voice.calls == [
        ("ฉันอยากกินข้าวเหนียวมะม่วงครับ", "voice-a"),
        ("ข้าวเหนียวมะม่วงครับ!", "voice-b"),
    ]
    assert e.has_audio(text.id, 0) and e.has_audio(text.id, 1)


def test_a_failed_line_stays_silent_and_the_text_is_still_served(tmp_path: Path) -> None:
    e = speaking_engine(tmp_path, FakeVoice(fail_on="ข้าวเหนียวมะม่วงครับ!"))
    topic = store.add_topic(e.conn, "Food stall", True, NOW)

    text = asyncio.run(e.next_text(topic.id))

    assert e.has_audio(text.id, 0)
    assert not e.has_audio(text.id, 1)


def test_missing_audio_is_made_on_request_and_then_cached(tmp_path: Path) -> None:
    e = speaking_engine(tmp_path, None)
    topic = store.add_topic(e.conn, "Food stall", True, NOW)
    text = asyncio.run(e.next_text(topic.id))
    assert asyncio.run(e.line_audio(text, 0)) is None  # no text to speech yet

    voice = FakeVoice()
    e.synthesize = voice
    path = asyncio.run(e.line_audio(text, 0))
    again = asyncio.run(e.line_audio(text, 0))

    assert path is not None and path.read_bytes().startswith(b"mp3:")
    assert again == path
    assert len(voice.calls) == 1
    assert asyncio.run(e.line_audio(text, 9)) is None
