"""Spanish: parsing, the checker, stretch words and rendering. The deck entries are real ones from
the Spanish deck (advanced words; everyday ones come from the common-words list)."""

import asyncio
import random
from typing import Any

from fake_anki import FakeAnki, card, note

from ailing import store
from ailing.coverage import check, parse_line
from ailing.difficulty import Difficulty
from ailing.engine import Engine
from ailing.generator import Line, TextRequest, generate
from ailing.languages import LANGUAGES
from ailing.lexicon import Entry, fetch_snapshot, lexicon_from
from ailing.reader import render
from ailing.spanish import common_words
from ailing.store import StoredText

ENTRIES = [
    Entry(1, "el blindaje", "armor plating / shielding", "mature"),
    Entry(2, "mantener a raya", "to keep at bay / to keep in check", "young", due=True),
    Entry(3, "a quemarropa", "point-blank", "mature"),
    Entry(4, "cerciorarse", "to make sure", "mature"),
    Entry(5, "diezmar", "to decimate", "young"),
    Entry(6, "la ojiva", "warhead", "mature"),
    Entry(7, "el enjambre", "swarm", "unreviewed"),
]
LEXICON = lexicon_from(ENTRIES, "es")


def statuses(text: str) -> dict[str, str]:
    return {t: LEXICON.status(t) for t in LEXICON.segment(text) if any(c.isalnum() for c in t)}


# ==== Parsing a model line ====


def test_bars_become_spaces_and_punctuation_stays_on_its_word() -> None:
    assert parse_line("¿Qué|quieres|*tomar*?", spaced=True) == ("¿Qué quieres tomar?", ["tomar"])
    assert parse_line("¡Hola|,|amigo|!", spaced=True)[0] == "¡Hola, amigo!"
    assert parse_line("¿|Vienes|?", spaced=True)[0] == "¿Vienes?"


def test_a_stretch_phrase_keeps_its_spaces() -> None:
    _, stretch = parse_line("Lo|*mantuvimos|a|raya*.", spaced=True)
    assert stretch == ["mantuvimos a raya"]


def test_thai_lines_are_parsed_as_before() -> None:
    assert parse_line("ฉัน|ต้องการ|*น้ำ*") == ("ฉันต้องการน้ำ", ["น้ำ"])


# ==== What counts as known ====


def test_common_words_count_as_known_in_any_form() -> None:
    assert "de" in common_words() and len(common_words()) == 10_000
    assert set(statuses("Hablaríamos con los niños mañana.").values()) == {"known"}


def test_deck_words_count_in_any_form_and_without_their_article() -> None:
    assert statuses("Las ojivas diezmaron la ciudad.") == {
        "Las": "known",
        "ojivas": "known",
        "diezmaron": "known",
        "la": "known",
        "ciudad": "known",
    }
    assert LEXICON.entry_of("ojivas") == "la ojiva"
    assert LEXICON.entry_of("blindaje") == "el blindaje"


def test_a_reflexive_verb_matches_its_forms_and_joined_pronouns_come_off() -> None:
    assert LEXICON.entry_of("cercioramos") == "cerciorarse"
    assert LEXICON.entry_of("cerciorándonos") == "cerciorarse"
    assert LEXICON.status("dámelo") == "known"  # dar, under me and lo


def test_a_rare_word_outside_the_deck_is_unknown() -> None:
    assert LEXICON.status("ornitorrinco") == "unknown"


def test_an_unreviewed_deck_word_is_not_known() -> None:
    assert LEXICON.status("enjambre") == "unknown"


def test_a_deck_phrase_is_one_token_even_inflected() -> None:
    pieces = LEXICON.segment("Los mantuvimos a raya, a quemarropa.")
    assert "mantuvimos a raya" in pieces
    assert "a quemarropa" in pieces
    assert LEXICON.entry_of("mantuvimos a raya") == "mantener a raya"
    assert LEXICON.status("mantuvimos a raya") == "known"


def test_a_rare_word_only_inside_a_deck_phrase_is_partial() -> None:
    assert LEXICON.status("quemarropa") == "partial"


def test_coverage_counts_a_phrase_once_and_flags_rare_words() -> None:
    coverage = check(["Los|mantuvimos|a|raya|con|un|ornitorrinco."], LEXICON)
    assert [t.text for t in coverage.tokens] == [
        "Los",
        "mantuvimos a raya",
        "con",
        "un",
        "ornitorrinco",
    ]
    assert coverage.words("unknown") == ["ornitorrinco"]
    assert coverage.ratio == 0.8


# ==== Stretch words ====


class Model:
    def __init__(self, *drafts: dict[str, Any]) -> None:
        self.drafts = list(drafts)

    async def __call__(self, messages: Any) -> Any:
        from ailing.generator import Usage

        return self.drafts.pop(0), [], Usage(1, 1, 0, 0)


def draft(*lines: str) -> dict[str, Any]:
    return {
        "title": "La noche",
        "roles": {"A": "Soldado", "B": "Capitán"},
        "lines": [
            {"speaker": "AB"[i % 2], "text": t, "english": "..."} for i, t in enumerate(lines)
        ],
        "glosses": [],
    }


def test_an_inflected_stretch_phrase_counts_as_the_entry_it_is_a_form_of() -> None:
    good = draft(
        "¿Lograron|*mantener|a|raya*|al|enemigo?",
        "Sí,|lo|*mantuvimos|a|raya*|toda|la|noche.",
    )
    request = TextRequest("guard duty", (ENTRIES[1], ENTRIES[4]), choose=1, language="es")
    result = asyncio.run(generate(Model(good), LEXICON, request))
    assert result.passed and result.floor_met
    assert result.stretch == ("mantener a raya",)
    assert result.glosses["mantener a raya"] == "to keep at bay / to keep in check"


# ==== Rendering ====


def test_a_spanish_text_renders_with_spaces_deck_flags_and_glosses_from_the_entry() -> None:
    text = StoredText(
        1,
        1,
        "t",
        (Line("A", "Las|*ojivas*|diezmaron|la|ciudad.", "..."),),
        {},
        ("la ojiva",),
        1.0,
        language="es",
    )
    out = render(text, LEXICON, {e.text: e.meaning for e in ENTRIES})
    words = out["lines"][0]["words"]
    assert "".join(w["text"] for w in words) == "Las ojivas diezmaron la ciudad."
    ojivas = next(w for w in words if w["text"] == "ojivas")
    assert ojivas == {
        "text": "ojivas",
        "status": "known",
        "gloss": "warhead",
        "stretch": True,
        "deck": True,
    }
    ciudad = next(w for w in words if w["text"] == "ciudad")
    assert ciudad["deck"] is False and ciudad["status"] == "known"
    assert out["language"] == "es"


# ==== Snapshot, storage and the engine ====


def test_the_spanish_snapshot_reads_the_spanish_deck() -> None:
    anki = FakeAnki([note(1, "el blindaje", "armor plating")], [card(1, 2, 30)])
    entries = asyncio.run(fetch_snapshot(anki, LANGUAGES["es"]))
    assert [(e.text, e.tier) for e in entries] == [("el blindaje", "mature")]
    queries = [args.get("query") or args.get("deck") for name, args in anki.calls]
    assert queries[0] == '"deck:👅 Languages::🌮 Español"'
    assert "👅 Languages::🌮 Español" in queries


def test_each_language_keeps_its_own_snapshot_and_difficulty() -> None:
    from datetime import datetime

    now = datetime(2026, 10, 26, 9, 0)
    conn = store.connect(":memory:")
    store.save_snapshot(conn, [Entry(100, "ฉัน", "I", "mature")], now)
    store.save_snapshot(conn, ENTRIES, now, "es")
    assert [e.text for e in store.load_snapshot(conn)[0]] == ["ฉัน"]
    assert len(store.load_snapshot(conn, "es")[0]) == len(ENTRIES)

    store.save_difficulty(conn, Difficulty(floor=0.97, stretch=1), "es")
    assert store.load_difficulty(conn) == Difficulty()
    assert store.load_difficulty(conn, "es") == Difficulty(floor=0.97, stretch=1)


SPANISH_DRAFT = draft(
    "¿Lograron|*mantener|a|raya*|al|enemigo?",
    "Sí,|lo|*mantuvimos|a|raya*|toda|la|noche.",
)


class ScriptedSpanish:
    def __init__(self) -> None:
        self.languages: list[str] = []

    def ask_for(self, entries: list[Entry], language: str) -> Any:
        self.languages.append(language)
        return Model(SPANISH_DRAFT, SPANISH_DRAFT, SPANISH_DRAFT)


def spanish_engine() -> tuple[Engine, ScriptedSpanish]:
    from datetime import datetime

    now = datetime(2026, 10, 26, 9, 0)
    conn = store.connect(":memory:")
    store.save_snapshot(conn, [Entry(100, "ฉัน", "I", "mature")], now)
    store.save_snapshot(conn, ENTRIES, now, "es")
    store.save_settings(conn, store.Settings(language="es"))
    model = ScriptedSpanish()
    return Engine(conn, model.ask_for, None, lambda: now, random.Random(1)), model


def test_with_spanish_chosen_a_topic_gets_a_spanish_text_and_thai_is_left_alone() -> None:
    e, model = spanish_engine()
    topic = store.add_topic(e.conn, "Guard duty", True, e.clock())

    text = asyncio.run(e.make_text(topic.id))

    assert text is not None and text.language == "es"
    assert model.languages == ["es"]
    assert store.list_topics(e.conn, "es")[0].ready == 1
    assert store.list_topics(e.conn, "th")[0].ready == 0


def test_a_rating_moves_the_difficulty_of_the_texts_language_only() -> None:
    e, _ = spanish_engine()
    topic = store.add_topic(e.conn, "Guard duty", True, e.clock())
    text = asyncio.run(e.make_text(topic.id))
    assert text is not None
    e.record_reading(text.id, store.Reading("too_hard", True, (), (), None, False, 60))
    assert store.load_difficulty(e.conn, "es").floor == 0.96
    assert store.load_difficulty(e.conn, "th") == Difficulty()
    row = e.conn.execute("SELECT language FROM readings").fetchone()
    assert row[0] == "spanish"


def test_spanish_lines_are_spoken_in_a_mexican_voice(tmp_path: Any) -> None:
    from ailing.tts import AudioCache

    spoken: list[tuple[str, str]] = []

    async def voice(text: str, name: str) -> bytes:
        spoken.append((text, name))
        return b"ID3"

    e, _ = spanish_engine()
    e.synthesize, e.audio = voice, AudioCache(tmp_path)
    topic = store.add_topic(e.conn, "Guard duty", True, e.clock())
    asyncio.run(e.make_text(topic.id))
    assert spoken[0] == ("¿Lograron mantener a raya al enemigo?", "es-MX-JorgeNeural")
    assert spoken[1][1] == "es-MX-DaliaNeural"


def test_switching_language_through_the_api_keeps_topics_and_separates_everything_else() -> None:
    import time

    from fastapi.testclient import TestClient

    from ailing.app import create_app

    e, _ = spanish_engine()
    store.save_settings(e.conn, store.Settings(language="th"))
    auth = {"Authorization": "Bearer p"}
    with TestClient(create_app(e, "p")) as c:
        topic = c.post("/api/topics", json={"name": "Guard duty", "favorite": False}, headers=auth)
        topic_id = topic.json()["id"]

        assert (
            c.patch("/api/settings", json={"language": "es"}, headers=auth).json()["language"]
            == "es"
        )
        deadline = time.time() + 10
        response = c.post(f"/api/topics/{topic_id}/next", headers=auth)
        while response.status_code == 202 and time.time() < deadline:
            time.sleep(0.02)
            response = c.post(f"/api/topics/{topic_id}/next", headers=auth)
        text = response.json()
        assert text["language"] == "es"
        assert text["title"] == "La noche"

        body = {"rating": "about_right", "finished": True}
        assert (
            c.post(f"/api/texts/{text['id']}/reading", json=body, headers=auth).status_code == 204
        )
        assert c.get("/api/progress", headers=auth).json()["finished"] == 1
        assert len(c.get("/api/texts", headers=auth).json()) == 1

        c.patch("/api/settings", json={"language": "th"}, headers=auth)
        assert [t["name"] for t in c.get("/api/topics", headers=auth).json()] == ["Guard duty"]
        assert c.get("/api/progress", headers=auth).json()["finished"] == 0
        assert c.get("/api/texts", headers=auth).json() == []
        assert c.patch("/api/settings", json={"language": "fr"}, headers=auth).status_code == 422
