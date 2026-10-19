import asyncio
from datetime import datetime, timedelta
from typing import Any

import pytest
from fake_anki import FakeAnki, card, note

from ailing.gateway import AnkiUnavailable, with_timeout
from ailing.lexicon import Entry
from ailing.store import (
    Settings,
    connect,
    is_stale,
    load_settings,
    load_snapshot,
    refresh_if_stale,
    save_settings,
    save_snapshot,
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
