from scripted import ENTRIES

from ailing.generator import Line
from ailing.lexicon import Entry, lexicon_from
from ailing.reader import render
from ailing.store import StoredText

TEXT = StoredText(
    id=7,
    topic_id=1,
    title="At the stall",
    lines=(Line("A", "ฉัน|อยาก|*ข้าวเหนียวมะม่วง*|ครับ!", "I'd like mango sticky rice."),),
    glosses={"ทอน": "give change"},
    stretch=("ข้าวเหนียวมะม่วง",),
    coverage=1.0,
)
MEANINGS = {e.text: e.meaning for e in ENTRIES}


def test_lines_are_split_by_the_server_with_status_and_gloss() -> None:
    out = render(TEXT, lexicon_from(ENTRIES), MEANINGS)
    words = out["lines"][0]["words"]
    assert [w["text"] for w in words] == ["ฉัน", "อยาก", "ข้าวเหนียวมะม่วง", "ครับ", "!"]
    mango = words[2]
    assert mango == {
        "text": "ข้าวเหนียวมะม่วง",
        "status": "known",
        "gloss": "mango sticky rice",
        "stretch": True,
    }
    assert words[4] == {"text": "!", "status": None, "gloss": None, "stretch": False}
    assert out["lines"][0]["english"] == "I'd like mango sticky rice."


def test_a_word_off_the_list_takes_the_models_gloss() -> None:
    text = StoredText(
        7, 1, "t", (Line("B", "ทอน|ครับ", "Here's your change."),), TEXT.glosses, (), 0.5
    )
    words = render(text, lexicon_from(ENTRIES), MEANINGS)["lines"][0]["words"]
    assert words[0] == {
        "text": "ทอน",
        "status": "unknown",
        "gloss": "give change",
        "stretch": False,
    }


def test_a_compound_of_deck_words_is_glossed_from_its_pieces() -> None:
    entries = [*ENTRIES, Entry(10, "ร้าน", "shop", "mature"), Entry(11, "อาหาร", "food", "mature")]
    text = StoredText(7, 1, "t", (Line("A", "ร้านอาหาร", "A restaurant."),), {}, (), 1.0)
    meanings = {e.text: e.meaning for e in entries}
    word = render(text, lexicon_from(entries), meanings)["lines"][0]["words"][0]
    assert word["text"] == "ร้านอาหาร"
    assert word["status"] == "known"
    assert word["gloss"] == "shop + food"
