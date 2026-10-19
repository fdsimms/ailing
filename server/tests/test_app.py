import random
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from scripted import BAD, ENTRIES, GOOD, ScriptedModel

from ailing import store
from ailing.app import create_app
from ailing.engine import Engine

NOW = datetime(2026, 10, 19, 9, 0)
AUTH = {"Authorization": "Bearer open sesame"}


def client(
    model: ScriptedModel | None = None, passphrase: str | None = "open sesame"
) -> TestClient:
    conn = store.connect(":memory:")
    store.save_snapshot(conn, ENTRIES, NOW)
    model = model or ScriptedModel(GOOD)
    engine = Engine(conn, model.ask_for, None, lambda: NOW, random.Random(1))
    return TestClient(create_app(engine, passphrase))


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

    text = c.post(f"/api/topics/{topic['id']}/next", headers=AUTH).json()

    assert text["title"] == "At the stall"
    first_line = text["lines"][0]
    assert first_line["speaker"] == "A"
    assert [w["text"] for w in first_line["words"]][:3] == ["ฉัน", "อยาก", "กิน"]
    assert text["stretch"] == ["ข้าวเหนียวมะม่วง"]


def test_next_text_explains_a_failed_generation() -> None:
    c = client(ScriptedModel(BAD))
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()
    response = c.post(f"/api/topics/{topic['id']}/next", headers=AUTH)
    assert response.status_code == 503
    assert "Couldn't write a text" in response.json()["detail"]


def test_next_text_for_a_missing_topic_is_404() -> None:
    assert client().post("/api/topics/99/next", headers=AUTH).status_code == 404


def test_logging_a_reading() -> None:
    c = client()
    topic = c.post("/api/topics", json={"name": "Food stall"}, headers=AUTH).json()
    text = c.post(f"/api/topics/{topic['id']}/next", headers=AUTH).json()

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
