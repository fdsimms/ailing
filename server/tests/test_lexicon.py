import asyncio

from fake_anki import FakeAnki, card, note

from ailing import lexicon
from ailing.lexicon import THAI_NOTES_QUERY, build_entries, clean, fetch_snapshot, lexicon_from

# Real entries and meanings from the Thai deck.
NOTES = [
    note(1772113047610, "ฉัน", "I; me (feminine)"),
    note(1788968359270, "รับอะไรดี", "what would you like? (server asking for order)"),
    note(1788968259380, "ข้าวเหนียวมะม่วง", "mango sticky rice"),
    note(1775529304199, "ดี", "good; well"),
]
CARDS = [
    card(1772113047610, 2, 320),
    card(1772113047610, 2, 286),
    card(1788968359270, 2, 5),
    card(1788968259380, 0, 0),
    card(1775529304199, 2, 40),
    card(1775529304199, 0, 0),
    card(9999, 2, 100),  # a Consonant Classes card: its note isn't in the Thai query
]


def test_entries_get_their_tier_from_their_cards() -> None:
    tiers = {e.text: e.tier for e in build_entries(NOTES, CARDS)}
    assert tiers == {
        "ฉัน": "mature",
        "รับอะไรดี": "young",
        "ข้าวเหนียวมะม่วง": "unreviewed",
        "ดี": "mature",
    }


def test_a_note_with_no_cards_is_unreviewed() -> None:
    assert build_entries([note(1, "ไป", "go")], [])[0].tier == "unreviewed"


def test_unreviewed_notes_are_not_known_for_coverage() -> None:
    known = lexicon_from(build_entries(NOTES, CARDS)).known
    assert known == {"ฉัน", "รับอะไรดี", "ดี"}


def test_clean_strips_html_and_entities() -> None:
    assert clean("<b>ไป</b>&nbsp;") == "ไป"
    assert clean("go <br>away") == "go away"


def test_an_empty_entry_is_skipped() -> None:
    assert build_entries([note(1, "<br>", "nothing")], []) == []


def test_fetch_pages_through_every_tool(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(lexicon, "FIND_NOTES_PAGE", 3)
    monkeypatch.setattr(lexicon, "NOTES_INFO_BATCH", 2)
    monkeypatch.setattr(lexicon, "CARDS_STATS_PAGE", 4)
    many = [note(i, f"คำ{i}", str(i)) for i in range(1, 8)]
    anki = FakeAnki(many, [card(i, 2, 30) for i in range(1, 8)])

    entries = asyncio.run(fetch_snapshot(anki))

    assert [e.note_id for e in entries] == list(range(1, 8))
    assert all(e.tier == "mature" for e in entries)
    counts = {name: sum(1 for n, _ in anki.calls if n == name) for name, _ in anki.calls}
    assert counts == {"find_notes": 3, "notes_info": 4, "cards_stats": 2}


def test_fetch_asks_for_the_thai_deck_without_the_consonant_cards() -> None:
    anki = FakeAnki(NOTES, CARDS)
    asyncio.run(fetch_snapshot(anki))
    find = next(args for name, args in anki.calls if name == "find_notes")
    assert find["query"] == THAI_NOTES_QUERY
    assert '-"deck:👅 Languages::🐘 ภาษาไทย::🏛 Consonant Classes"' in THAI_NOTES_QUERY
