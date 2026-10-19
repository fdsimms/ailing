import random

from ailing.lexicon import Entry
from ailing.stretch import pick_stretch

ENTRIES = [
    Entry(1, "ฉัน", "I", "mature"),
    Entry(2, "ดี", "good", "mature", due=True),
    Entry(3, "ไป", "go", "young"),
    Entry(4, "มา", "come", "young", due=True),
    Entry(5, "ทอน", "give change", "unreviewed", due=True),
]


def test_due_words_come_first_then_young() -> None:
    picked = pick_stretch(ENTRIES, 3, random.Random(1))
    assert {e.text for e in picked[:2]} == {"ดี", "มา"}
    assert picked[2].text == "ไป"


def test_mature_words_that_are_not_due_and_unreviewed_words_are_never_picked() -> None:
    picked = {e.text for e in pick_stretch(ENTRIES, 10, random.Random(1))}
    assert picked == {"ดี", "มา", "ไป"}


def test_count_is_respected() -> None:
    assert len(pick_stretch(ENTRIES, 1, random.Random(1))) == 1
    assert pick_stretch(ENTRIES, 0, random.Random(1)) == []
