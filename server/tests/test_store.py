import asyncio
from datetime import datetime, timedelta
from typing import Any

import pytest
from fake_anki import FakeAnki, card, note

from ailing.gateway import AnkiUnavailable, with_timeout
from ailing.lexicon import Entry
from ailing.store import (
    Settings,
    add_topic,
    connect,
    get_text,
    is_stale,
    load_settings,
    load_snapshot,
    refresh_if_stale,
    save_settings,
    save_snapshot,
    save_text,
)

NOW = datetime(2026, 10, 19, 9, 0)
OLD = [Entry(1, "ฉัน", "I; me", "mature")]


@pytest.fixture
def conn():  # type: ignore[no-untyped-def]
    return connect(":memory:")


def test_round_trip(conn) -> None:  # type: ignore[no-untyped-def]
    save_snapshot(conn, OLD, NOW)
    assert load_snapshot(conn) == (OLD, NOW)


def test_a_new_snapshot_replaces_the_old_one(conn) -> None:  # type: ignore[no-untyped-def]
    save_snapshot(conn, OLD, NOW)
    save_snapshot(conn, [Entry(2, "ดี", "good", "young")], NOW)
    assert [e.text for e in load_snapshot(conn)[0]] == ["ดี"]


def test_staleness() -> None:
    assert is_stale(None, NOW)
    assert not is_stale(NOW - timedelta(hours=23), NOW)
    assert is_stale(NOW - timedelta(hours=24), NOW)


def test_refreshes_when_stale(conn) -> None:  # type: ignore[no-untyped-def]
    anki = FakeAnki([note(2, "ดี", "good")], [card(2, 2, 30)])
    assert asyncio.run(refresh_if_stale(conn, anki, NOW))
    assert load_snapshot(conn) == ([Entry(2, "ดี", "good", "mature")], NOW)


def test_does_not_call_anki_when_fresh(conn) -> None:  # type: ignore[no-untyped-def]
    save_snapshot(conn, OLD, NOW - timedelta(hours=1))
    anki = FakeAnki([], [])
    assert not asyncio.run(refresh_if_stale(conn, anki, NOW))
    assert anki.calls == []


def test_keeps_yesterdays_snapshot_when_anki_hangs(conn) -> None:  # type: ignore[no-untyped-def]
    save_snapshot(conn, OLD, NOW - timedelta(days=1))

    async def hangs(name: str, args: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(10)
        return {}

    assert not asyncio.run(refresh_if_stale(conn, with_timeout(hangs, seconds=0.01), NOW))
    assert load_snapshot(conn) == (OLD, NOW - timedelta(days=1))


def test_keeps_the_old_snapshot_when_anki_returns_nothing(conn) -> None:  # type: ignore[no-untyped-def]
    save_snapshot(conn, OLD, NOW - timedelta(days=1))
    assert not asyncio.run(refresh_if_stale(conn, FakeAnki([], []), NOW))
    assert load_snapshot(conn)[0] == OLD


def test_any_failure_becomes_anki_unavailable() -> None:
    async def breaks(name: str, args: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError("tunnel down")

    async def call() -> dict[str, Any]:
        return await with_timeout(breaks)("find_notes", {})

    with pytest.raises(AnkiUnavailable, match="tunnel down"):
        asyncio.run(call())


def test_the_default_timeout_is_45_seconds() -> None:
    from ailing.gateway import TIMEOUT_SECONDS

    assert TIMEOUT_SECONDS == 45


def test_a_reply_of_the_wrong_shape_keeps_the_old_snapshot(conn) -> None:  # type: ignore[no-untyped-def]
    save_snapshot(conn, OLD, NOW - timedelta(days=1))

    async def odd(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"unexpected": True}

    assert not asyncio.run(refresh_if_stale(conn, odd, NOW))
    assert load_snapshot(conn)[0] == OLD


def test_settings_default_to_choosing_stretch_words_and_round_trip(conn) -> None:  # type: ignore[no-untyped-def]
    assert load_settings(conn) == Settings(stretch_words="topic")
    save_settings(conn, Settings(stretch_words="any"))
    assert load_settings(conn).stretch_words == "any"


def test_a_setting_that_no_longer_exists_is_ignored(conn) -> None:  # type: ignore[no-untyped-def]
    conn.execute("INSERT INTO meta (key, value) VALUES ('settings', '{\"retired\": 1}')")
    assert load_settings(conn) == Settings()


def test_a_text_keeps_its_speakers_roles(conn) -> None:  # type: ignore[no-untyped-def]
    from test_generator import GOOD, MANGO, ScriptedModel, run

    from ailing.generator import TextRequest

    generated = run(ScriptedModel(GOOD), TextRequest("food", (MANGO,)))
    topic = add_topic(conn, "food", True, NOW)
    text_id = save_text(conn, topic.id, generated, [], 0.95, NOW)
    stored = get_text(conn, text_id)
    assert stored is not None and stored.roles == {"A": "Vendor", "B": "Customer"}


def test_a_database_from_before_roles_gains_the_column(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "old.db"
    first = connect(path)
    first.execute("ALTER TABLE texts DROP COLUMN roles")
    first.commit()
    first.close()
    columns = {r[1] for r in connect(path).execute("PRAGMA table_info(texts)")}
    assert "roles" in columns


def test_a_word_marked_again_after_clearing_is_listed_again(conn) -> None:  # type: ignore[no-untyped-def]
    from scripted import GOOD

    from ailing.coverage import check
    from ailing.generator import Generated, Line
    from ailing.lexicon import lexicon_from
    from ailing.store import Reading, clear_word, log_reading, marked_words

    topic = add_topic(conn, "Food", True, NOW)
    lines = tuple(Line(ln["speaker"], ln["text"], ln["english"]) for ln in GOOD["lines"])
    coverage = check([ln.text for ln in lines], lexicon_from(OLD))
    generated = Generated("t", lines, {"ทอน": "change"}, coverage, 1, True, ())

    def reading_at(at: datetime) -> None:
        text_id = save_text(conn, topic.id, generated, [], 0.95, at)
        log_reading(conn, text_id, Reading(None, True, (), ("ทอน",), None, False, 10), at)

    reading_at(NOW)
    clear_word(conn, "ทอน", NOW + timedelta(minutes=1))
    assert marked_words(conn) == []

    reading_at(NOW + timedelta(days=1))
    [word] = marked_words(conn)
    assert (word.word, word.times, word.glosses["ทอน"]) == ("ทอน", 1, "change")


def test_a_database_from_before_removing_topics_gains_the_column(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE topics (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,"
        " favorite INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)"
    )
    old.execute("INSERT INTO topics (name, created_at) VALUES ('Taxi', '2026-10-19')")
    old.commit()
    old.close()

    from ailing.store import list_topics

    assert [t.name for t in list_topics(connect(path))] == ["Taxi"]


def test_a_database_from_before_stories_reads_its_texts_as_dialogues(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import sqlite3

    path = tmp_path / "old.db"
    conn = connect(path)
    topic = add_topic(conn, "Food", True, NOW)
    conn.execute("ALTER TABLE texts DROP COLUMN form")
    conn.execute(
        "INSERT INTO texts (topic_id, created_at, title, lines, glosses, stretch, coverage,"
        " token_count, floor, attempts, model, input_tokens, output_tokens, cache_read_tokens,"
        " cache_write_tokens, cost_usd) VALUES (?, '2026-10-19', 't', '[]', '{}', '[]', 1, 0,"
        " 0.95, 1, 'm', 0, 0, 0, 0, 0)",
        (topic.id,),
    )
    conn.commit()
    conn.close()
    assert "form" not in {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(texts)")}

    text = get_text(connect(path), 1)
    assert text is not None and text.form == "dialogue"
