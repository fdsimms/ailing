import pytest

from ailing.coverage import FLOOR, Lexicon, check, parse_line

# The four phrases are real entries in the Thai deck, and the brief's feasibility test called out the
# words inside them (ข้าวเหนียว, รับ, เก็บ, ตุ๊กตุ๊ก) as false misses: the deck has them only inside
# these phrases. ทอน is a word the deck lacks entirely.
DECK = [
    "ข้าวเหนียวมะม่วง",
    "รับอะไรดี",
    "เก็บเงิน",
    "รถตุ๊กตุ๊ก",
    "ฉัน",
    "อยาก",
    "กิน",
    "ครับ",
    "ร้าน",
    "อาหาร",
    "บาท",
    "ไป",
    "ไหน",
    "มะม่วง",
]


@pytest.fixture(scope="module")
def lexicon() -> Lexicon:
    return Lexicon(DECK)


def statuses(lines: list[str], lexicon: Lexicon) -> dict[str, str]:
    return {t.text: t.status for t in check(lines, lexicon).tokens}


def test_a_deck_phrase_stays_one_known_token(lexicon: Lexicon) -> None:
    assert statuses(["ฉันอยากกินข้าวเหนียวมะม่วงครับ"], lexicon) == {
        "ฉัน": "known",
        "อยาก": "known",
        "กิน": "known",
        "ข้าวเหนียวมะม่วง": "known",
        "ครับ": "known",
    }


@pytest.mark.parametrize("word", ["ข้าวเหนียว", "รับ", "เก็บ", "ตุ๊กตุ๊ก"])
def test_a_word_only_inside_a_deck_phrase_is_partial(lexicon: Lexicon, word: str) -> None:
    assert word in lexicon.partial
    assert statuses([f"ฉัน{word}ครับ"], lexicon)[word] == "partial"


def test_partial_counts_as_unknown_for_coverage(lexicon: Lexicon) -> None:
    result = check(["ฉันกินข้าวเหนียว"], lexicon)
    assert (result.known, result.counted) == (2, 3)
    assert result.words("partial") == ["ข้าวเหนียว"]


def test_a_word_inside_a_phrase_that_is_also_an_entry_is_not_partial(lexicon: Lexicon) -> None:
    assert "มะม่วง" not in lexicon.partial
    assert "รถ" in lexicon.partial


def test_partial_is_found_by_segmenting_not_by_substring(lexicon: Lexicon) -> None:
    # ครับ contains the letters of รับ, but รับ isn't a word inside it.
    assert statuses(["ครับ"], lexicon) == {"ครับ": "known"}


def test_a_word_outside_the_deck_is_unknown(lexicon: Lexicon) -> None:
    result = check(["ฉัน|ทอน|ครับ"], lexicon)
    assert result.words("unknown") == ["ทอน"]
    assert result.words("partial") == []


def test_a_token_that_splits_into_entries_is_known(lexicon: Lexicon) -> None:
    # ร้านอาหาร is one word in PyThaiNLP's dictionary; the deck has ร้าน and อาหาร.
    assert statuses(["ร้านอาหาร"], lexicon) == {"ร้านอาหาร": "known"}


def test_numbers_are_known_and_spaces_and_punctuation_are_not_counted(lexicon: Lexicon) -> None:
    result = check(["25 บาท ครับ!", "๑๐๐ บาท"], lexicon)
    assert [t.text for t in result.tokens] == ["25", "บาท", "ครับ", "๑๐๐", "บาท"]
    assert result.ratio == 1.0


def test_the_models_word_breaks_are_ignored(lexicon: Lexicon) -> None:
    # The model glued an unknown word onto a known one. Re-segmenting catches it.
    result = check(["ฉัน|กินทอน|ครับ"], lexicon)
    assert "ทอน" in result.words("unknown")
    assert not result.meets()


def test_stretch_words_are_read_from_asterisks() -> None:
    assert parse_line("ฉัน|ต้องการ|*น้ำ*") == ("ฉันต้องการน้ำ", ["น้ำ"])


def test_spaces_between_thai_characters_are_dropped() -> None:
    assert parse_line("สวัสดี ค่ะ|รับอะไรดี คะ?")[0] == "สวัสดีค่ะรับอะไรดีคะ?"
    assert parse_line("OK ค่ะ")[0] == "OK ค่ะ"


def test_stretch_words_are_listed_once_in_order(lexicon: Lexicon) -> None:
    result = check(["*ทอน*|ครับ", "ฉัน|*เก็บ*|*ทอน*"], lexicon)
    assert result.stretch_words == ("ทอน", "เก็บ")


def test_floor() -> None:
    lexicon = Lexicon(["ฉัน"])
    nineteen_known = ["ฉัน"] * 19
    assert check([*nineteen_known, "ทอน"], lexicon).meets(FLOOR)
    assert not check([*nineteen_known[:18], "ทอน"], lexicon).meets(FLOOR)


def test_empty_text_does_not_pass() -> None:
    assert not check([], Lexicon(["ฉัน"])).meets()
