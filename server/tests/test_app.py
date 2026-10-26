import random
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from scripted import BAD, ENTRIES, GOOD, ScriptedModel

from ailing import store
from ailing.app import create_app
from ailing.engine import Engine

NOW = datetime(2026, 10, 19, 9, 0)
AUTH = {"Authorization": "Bearer open sesame"}


_open: list[TestClient] = []


@pytest.fixture(autouse=True)
def _close_clients() -> Iterator[None]:
    yield
    while _open:
        _open.pop().__exit__(None, None, None)


def started(app: Any) -> TestClient:
    # Entered, so the event loop (and the background writes started on it) outlives each request.
    c = TestClient(app)
    c.__enter__()
    _open.append(c)
    return c


def client(
    model: ScriptedModel | None = None, passphrase: str | None = "open sesame"
) -> TestClient:
    conn = store.connect(":memory:")
    store.save_snapshot(conn, ENTRIES, NOW)
    model = model or ScriptedModel(GOOD)
    engine = Engine(conn, model.ask_for, None, lambda: NOW, random.Random(1))
    return started(create_app(engine, passphrase))


def next_text(c: TestClient, topic_id: int) -> Any:
    """What the app does: ask, and while the answer is 202, ask again shortly."""
    deadline = time.time() + 10
    while True:
        response = c.post(f"/api/topics/{topic_id}/next", headers=AUTH)
        if response.status_code != 202 or time.time() > deadline:
            return response
        time.sleep(0.02)


def test_health_needs_no_passphrase() -> None:
    assert client().get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "x"}])
def test_api_routes_refuse_a_missing_or_wrong_passphrase(headers: dict[str, str]) -> None:
    c = client()
    assert c.get("/api/check", headers=headers).status_code == 401
    assert c.get("/api/topics", headers=headers).status_code == 401


def test_the_right_passphrase_checks_out() -> None:
    assert client().get("/api/check", headers=AUTH).status_code == 204


def test_no_passphrase_configured_refuses_everything() -> None:
    c = client(passphrase=None)
    response = c.get("/api/check", headers={"Authorization": "Bearer "})
    assert response.status_code == 503
    assert response.json()["detail"] == "The server has no passphrase set."


def test_adding_a_topic_tops_it_up_in_the_background() -> None:
    model = ScriptedModel(GOOD)
    c = client(model)

    added = c.post("/api/topics", json={"name": "  Food   stall "}, headers=AUTH).json()

    assert added["name"] == "Food stall"
    assert added["favorite"] is True
    assert c.get("/api/topics", headers=AUTH).json()[0]["ready"] == 1
    assert model.calls == 1


def test_adding_the_same_topic_twice_returns_the_first() -> None:
    c = client()
    first = c.post("/api/topics", json={"name": "Taxi"}, headers=AUTH).json()
    second = c.post("/api/topics", json={"name": "taxi"}, headers=AUTH).json()
    assert first["id"] == second["id"]


def test_a_topic_can_be_unfavorited() -> None:
    c = client()
    topic = c.post("/api/topics", json={"name": "Taxi"}, headers=AUTH).json()
    updated = c.patch(f"/api/topics/{topic['id']}", json={"favorite": False}, headers=AUTH)
    assert updated.json()["favorite"] is False
    assert c.patch("/api/topics/99", json={"favorite": False}, headers=AUTH).status_code == 404


def test_next_text_returns_the_server_split_lines() -> None:
    c = client()
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()

    text = next_text(c, topic["id"]).json()

    assert text["title"] == "At the stall"
    first_line = text["lines"][0]
    assert first_line["speaker"] == "A"
    assert [w["text"] for w in first_line["words"]][:3] == ["ฉัน", "อยาก", "กิน"]
    assert text["stretch"] == ["ข้าวเหนียวมะม่วง"]


def test_next_text_explains_a_failed_generation() -> None:
    c = client(ScriptedModel(BAD))
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()
    response = next_text(c, topic["id"])
    assert response.status_code == 503
    assert "Couldn't write a text" in response.json()["detail"]
    assert c.get("/api/topics", headers=AUTH).json()[0]["state"] == "failed"


def test_next_text_for_a_missing_topic_is_404() -> None:
    assert client().post("/api/topics/99/next", headers=AUTH).status_code == 404


def test_logging_a_reading() -> None:
    c = client()
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()
    text = next_text(c, topic["id"]).json()

    response = c.post(
        f"/api/texts/{text['id']}/reading",
        json={
            "rating": "about_right",
            "finished": True,
            "words_glossed": ["กิน"],
            "words_flagged": ["ครับ"],
            "audio_speed": 0.8,
            "seconds": 95,
        },
        headers=AUTH,
    )

    assert response.status_code == 204
    assert c.post("/api/texts/999/reading", json={}, headers=AUTH).status_code == 404
    assert (
        c.post(f"/api/texts/{text['id']}/reading", json={"rating": "meh"}, headers=AUTH).status_code
        == 422
    )


def speaking_client(tmp_path: Path) -> TestClient:
    from ailing.tts import AudioCache

    async def voice(text: str, name: str) -> bytes:
        return b"ID3" + text.encode()

    conn = store.connect(":memory:")
    store.save_snapshot(conn, ENTRIES, NOW)
    engine = Engine(
        conn,
        ScriptedModel(GOOD).ask_for,
        None,
        lambda: NOW,
        random.Random(1),
        synthesize=voice,
        audio=AudioCache(tmp_path),
    )
    return started(create_app(engine, "open sesame"))


def test_lines_say_whether_they_have_audio() -> None:
    c = client()  # no text to speech set up
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()
    text = next_text(c, topic["id"]).json()
    assert [line["audio"] for line in text["lines"]] == [False, False]


def test_a_lines_audio_is_served_as_mp3(tmp_path: Path) -> None:
    c = speaking_client(tmp_path)
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()
    text = next_text(c, topic["id"]).json()
    assert all(line["audio"] for line in text["lines"])

    response = c.get(f"/api/texts/{text['id']}/lines/0/audio", headers=AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content.startswith(b"ID3")
    assert c.get(f"/api/texts/{text['id']}/lines/0/audio").status_code == 401
    assert c.get(f"/api/texts/{text['id']}/lines/9/audio", headers=AUTH).status_code == 404
    assert c.get("/api/texts/999/lines/0/audio", headers=AUTH).status_code == 404


def test_a_topic_with_nothing_ready_answers_202_then_the_text() -> None:
    c = client()
    topic = c.post("/api/topics", json={"name": "Taxi", "favorite": False}, headers=AUTH).json()
    assert topic["state"] == "idle"

    first = c.post(f"/api/topics/{topic['id']}/next", headers=AUTH)
    assert first.status_code == 202
    assert first.json() == {"writing": True}

    text = next_text(c, topic["id"])
    assert text.status_code == 200
    assert text.json()["title"] == "At the stall"


def test_topics_report_their_state() -> None:
    c = client()
    c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH)
    c.post("/api/topics", json={"name": "Taxi", "favorite": False}, headers=AUTH)
    states = {t["name"]: t["state"] for t in c.get("/api/topics", headers=AUTH).json()}
    assert states == {"Food stall": "ready", "Taxi": "idle"}


def test_a_passphrase_with_non_ascii_characters_works() -> None:
    conn = store.connect(":memory:")
    engine = Engine(conn, None, None, lambda: NOW)
    c = started(create_app(engine, "pässword"))
    utf8 = "Bearer pässword".encode()  # the bytes a phone sends
    assert c.get("/api/check", headers={b"Authorization": utf8}).status_code == 204
    assert c.get("/api/check", headers={"Authorization": "Bearer password"}).status_code == 401


def test_a_repeated_reading_is_accepted_but_counted_once() -> None:
    c = client()
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()
    text = next_text(c, topic["id"]).json()
    body = {"rating": "too_hard", "finished": True}
    assert c.post(f"/api/texts/{text['id']}/reading", json=body, headers=AUTH).status_code == 204
    assert c.post(f"/api/texts/{text['id']}/reading", json=body, headers=AUTH).status_code == 204


def test_the_stretch_setting_can_be_read_and_changed() -> None:
    c = client()
    assert c.get("/api/settings", headers=AUTH).json() == {
        "stretch_words": "topic",
        "lines": 8,
        "form": "dialogue",
        "language": "th",
    }
    changed = c.patch("/api/settings", headers=AUTH, json={"stretch_words": "any"})
    assert changed.json() == {
        "stretch_words": "any",
        "lines": 8,
        "form": "dialogue",
        "language": "th",
    }
    assert c.get("/api/settings", headers=AUTH).json() == {
        "stretch_words": "any",
        "lines": 8,
        "form": "dialogue",
        "language": "th",
    }
    assert (
        c.patch("/api/settings", headers=AUTH, json={"stretch_words": "loose"}).status_code == 422
    )
    assert c.get("/api/settings").status_code == 401


def test_a_removed_topic_leaves_the_list_and_comes_back_when_added_again() -> None:
    c = client()
    topic = c.post("/api/topics", json={"name": "Taxi", "favorite": False}, headers=AUTH).json()

    assert c.delete(f"/api/topics/{topic['id']}", headers=AUTH).status_code == 204
    assert c.get("/api/topics", headers=AUTH).json() == []
    assert c.post(f"/api/topics/{topic['id']}/next", headers=AUTH).status_code == 404
    assert c.delete(f"/api/topics/{topic['id']}", headers=AUTH).status_code == 404

    again = c.post("/api/topics", json={"name": "taxi"}, headers=AUTH).json()
    assert again["id"] == topic["id"]
    assert again["favorite"] is True
    assert [t["name"] for t in c.get("/api/topics", headers=AUTH).json()] == ["Taxi"]


def read(c: TestClient, rating: str | None, flagged: list[str], finished: bool = True) -> None:
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()
    text = next_text(c, topic["id"]).json()
    body = {"rating": rating, "finished": finished, "words_flagged": flagged}
    assert c.post(f"/api/texts/{text['id']}/reading", json=body, headers=AUTH).status_code == 204


def test_progress_counts_finished_texts_and_says_how_hard_the_next_is() -> None:
    c = client()
    empty = c.get("/api/progress", headers=AUTH).json()
    assert empty["finished"] == 0
    assert empty["median_coverage"] is None
    assert empty["next"] == {"floor": 0.95, "stretch": 2}

    read(c, "about_right", [])
    read(c, "too_hard", [])
    read(c, None, [], finished=False)  # backed out of: not counted

    progress = c.get("/api/progress", headers=AUTH).json()
    assert progress["days"] == 14
    assert progress["finished"] == 2
    assert progress["median_coverage"] == 1.0
    assert progress["ratings"] == {"too_easy": 0, "about_right": 1, "too_hard": 1, "none": 0}
    assert progress["next"] == {"floor": 0.96, "stretch": 1}
    assert c.get("/api/progress").status_code == 401


def test_marked_words_are_listed_with_glosses_until_cleared() -> None:
    c = client()
    read(c, None, ["ครับ"])
    read(c, None, ["ครับ", "ข้าวเหนียวมะม่วง"])

    words = c.get("/api/words", headers=AUTH).json()
    assert [(w["word"], w["times"], w["status"]) for w in words] == [
        ("ครับ", 2, "known"),
        ("ข้าวเหนียวมะม่วง", 1, "known"),
    ]
    assert words[0]["gloss"] == "polite particle (male)"

    assert c.post("/api/words/clear", json={"word": "ครับ"}, headers=AUTH).status_code == 204
    assert [w["word"] for w in c.get("/api/words", headers=AUTH).json()] == ["ข้าวเหนียวมะม่วง"]
    assert c.get("/api/words").status_code == 401


def test_the_length_setting_can_be_changed_to_a_length_offered() -> None:
    c = client()
    changed = c.patch("/api/settings", headers=AUTH, json={"lines": 12})
    assert changed.json() == {
        "stretch_words": "topic",
        "lines": 12,
        "form": "dialogue",
        "language": "th",
    }
    assert c.patch("/api/settings", headers=AUTH, json={"lines": 30}).status_code == 422


def test_past_texts_lists_texts_read_to_the_end_and_serves_them_again() -> None:
    c = client()
    assert c.get("/api/texts", headers=AUTH).json() == []
    read(c, "about_right", [])
    read(c, None, [], finished=False)

    [past] = c.get("/api/texts", headers=AUTH).json()
    assert (past["topic"], past["title"], past["rating"]) == (
        "Food stall",
        "At the stall",
        "about_right",
    )

    again = c.get(f"/api/texts/{past['id']}", headers=AUTH).json()
    assert again["title"] == "At the stall"
    assert [w["text"] for w in again["lines"][0]["words"]][:3] == ["ฉัน", "อยาก", "กิน"]
    assert c.get("/api/texts/999", headers=AUTH).status_code == 404
    assert c.get("/api/texts").status_code == 401


def test_suggestions_leave_out_topics_already_added_or_removed() -> None:
    c = client()
    first = c.get("/api/suggestions", headers=AUTH).json()
    assert {"name", "fit"} <= set(first[0])

    taken = c.post("/api/topics", json={"name": first[0]["name"]}, headers=AUTH).json()
    removed = c.post("/api/topics", json={"name": first[1]["name"]}, headers=AUTH).json()
    c.delete(f"/api/topics/{removed['id']}", headers=AUTH)

    names = [s["name"] for s in c.get("/api/suggestions", headers=AUTH).json()]
    assert taken["name"] not in names
    assert removed["name"] not in names
    assert len(names) == len(first) - 2
    assert c.get("/api/suggestions").status_code == 401


def test_the_form_setting_can_be_set_to_story() -> None:
    c = client()
    changed = c.patch("/api/settings", headers=AUTH, json={"form": "story"})
    assert changed.json()["form"] == "story"
    assert c.patch("/api/settings", headers=AUTH, json={"form": "poem"}).status_code == 422


def test_a_text_says_what_form_it_is() -> None:
    c = client()
    read(c, "about_right", [])
    [past] = c.get("/api/texts", headers=AUTH).json()
    assert past["form"] == "dialogue"
    assert c.get(f"/api/texts/{past['id']}", headers=AUTH).json()["form"] == "dialogue"
