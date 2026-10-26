from scripted import ENTRIES

from ailing.lexicon import lexicon_from
from ailing.suggestions import IDEAS, suggest

LEXICON = lexicon_from(ENTRIES)


def test_every_idea_is_offered_when_nothing_is_taken() -> None:
    assert len(suggest(LEXICON, set())) == len(IDEAS)


def test_ideas_whose_words_the_deck_knows_come_first() -> None:
    # The sample deck knows กิน and ฉัน and little else, so food ideas that use กิน lead.
    first = suggest(LEXICON, set())[0]
    assert first.name in {"Ordering street food", "At the pharmacy"}
    assert first.fit > 0
    assert suggest(LEXICON, set())[-1].fit == 0


def test_ties_keep_the_listed_order() -> None:
    unknown = [s.name for s in suggest(LEXICON, set()) if s.fit == 0]
    listed = [i.name for i in IDEAS if i.name in unknown]
    assert unknown == listed


def test_taken_names_are_left_out_ignoring_case() -> None:
    names = {s.name for s in suggest(LEXICON, {"at a coffee shop"})}
    assert "At a coffee shop" not in names


def test_idea_names_are_unique_and_each_has_words() -> None:
    assert len({i.name.casefold() for i in IDEAS}) == len(IDEAS)
    assert all(len(i.words) >= 4 for i in IDEAS)
