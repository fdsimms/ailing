"""Coverage checker: what share of a text's words are already known from the deck.

The lexicon is the dictionary. A text is segmented with the deck's entries added to PyThaiNLP's
word list, so a deck phrase (ข้าวเหนียวมะม่วง) stays one token instead of being split into words the
deck doesn't hold on their own. The model's own `|` breaks are never used for coverage: they're
stripped and the line is segmented again here, so a known word glued to an unknown one can't pass.

Each counted token is one of:
- known: a deck entry, a number, or a token that splits cleanly into deck entries (ร้านอาหาร when
  the deck holds ร้าน and อาหาร)
- partial: not an entry itself, but a word inside a longer entry (รับ inside รับอะไรดี). Counts as
  unknown for coverage, per the brief
- unknown: anything else
Whitespace and punctuation aren't counted.

`Lexicon` is Thai's checker. Spanish has its own (spanish.py); both fit `Checker`, which is all the
generator, the reader and `check` need.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from typing import Literal, Protocol

from pythainlp.corpus import thai_words
from pythainlp.tokenize import word_tokenize
from pythainlp.util import dict_trie

FLOOR = 0.95
TARGET = 0.98
# Below the floor after every attempt, the closest attempt is still shown if it's at least this
# (the owner's decision, 26 October 2026; docs/architecture.md, Generation and coverage). At 90%,
# listening comprehension already varied widely between people (docs/brief.md, evidence table).
MINIMUM = 0.90

Status = Literal["known", "partial", "unknown"]

_NUMBER = re.compile(r"^[0-9๐-๙]+([.,][0-9๐-๙]+)*$")
# A token with no letters or digits at all: spaces, punctuation, ๆ and ฯ.
_NOT_A_WORD = re.compile(r"^[\W_ๆฯ]+$")


# Whitespace with a Thai character on each side.
_BETWEEN_THAI = re.compile(r"(?<=[฀-๿])\s+(?=[฀-๿])")
# In a spaced language, the space a `|` became before closing punctuation or after opening.
_SPACE_BEFORE_CLOSING = re.compile(r"\s+(?=[.,;:!?)\]»…])")
_SPACE_AFTER_OPENING = re.compile(r"(?<=[¿¡(\[«])\s+")


@dataclass(frozen=True)
class Token:
    text: str
    status: Status


@dataclass(frozen=True)
class Coverage:
    tokens: tuple[Token, ...]
    stretch_words: tuple[str, ...]

    @property
    def counted(self) -> int:
        return len(self.tokens)

    @property
    def known(self) -> int:
        return sum(1 for t in self.tokens if t.status == "known")

    @property
    def ratio(self) -> float:
        return self.known / self.counted if self.counted else 0.0

    def words(self, status: Status) -> list[str]:
        """Distinct words with this status, in the order they first appear."""
        return list(dict.fromkeys(t.text for t in self.tokens if t.status == status))

    def meets(self, floor: float = FLOOR) -> bool:
        return self.ratio >= floor


class Checker(Protocol):
    """What a language's coverage checker provides."""

    known: frozenset[str]  # the deck entries counted as known
    spaced: bool  # whether the language puts spaces between words

    def segment(self, text: str) -> list[str]: ...

    def status(self, token: str) -> Status: ...

    def known_pieces(self, token: str) -> list[str] | None: ...

    def entry_of(self, token: str) -> str | None:
        """The deck entry this token is a form of (hablé for hablar), or None."""
        ...


class Lexicon:
    """Thai: the deck's entries are the dictionary, and only they count as known."""

    spaced = False

    def __init__(self, known: Iterable[str]) -> None:
        self.known = frozenset(w.strip() for w in known if w.strip())

    @cached_property
    def partial(self) -> frozenset[str]:
        """Words that appear only inside a longer entry. Found by segmenting each entry with the
        default dictionary, not by substring, so ครับ never yields รับ."""
        pieces = {p for entry in self.known for p in word_tokenize(entry, engine="newmm")}
        return frozenset(
            p for p in pieces if p not in self.known and _counts(p) and not _is_number(p)
        )

    @cached_property
    def _segmenter(self):  # type: ignore[no-untyped-def]
        return dict_trie(set(thai_words()) | self.known | self.partial)

    @cached_property
    def _known_only(self):  # type: ignore[no-untyped-def]
        return dict_trie(self.known)

    def segment(self, text: str) -> list[str]:
        return list(word_tokenize(text, custom_dict=self._segmenter, engine="newmm"))

    def status(self, token: str) -> Status:
        if token in self.known or _is_number(token):
            return "known"
        if token in self.partial:
            return "partial"
        if self._splits_into_known(token):
            return "known"
        return "unknown"

    def known_pieces(self, token: str) -> list[str] | None:
        """The deck entries a known compound splits into (ร้านอาหาร into ร้าน, อาหาร), or None if it
        doesn't split cleanly into two or more."""
        pieces = list(word_tokenize(token, custom_dict=self._known_only, engine="newmm"))
        if len(pieces) > 1 and all(p in self.known or _is_number(p) for p in pieces):
            return pieces
        return None

    def _splits_into_known(self, token: str) -> bool:
        return self.known_pieces(token) is not None

    def entry_of(self, token: str) -> str | None:
        return token if token in self.known else None


def parse_line(line: str, spaced: bool = False) -> tuple[str, list[str]]:
    """A model line (`ฉัน|ต้องการ|*น้ำ*`) as plain text plus its stretch words. Thai is written
    without spaces, so any the model adds between Thai characters are dropped. In a spaced language
    (`¿Qué|quieres|*tomar*?`) each `|` stands for a space, and punctuation stays on its word."""
    joiner = " " if spaced else ""

    def join(text: str) -> str:
        text = text.replace("*", "").replace("|", joiner)
        if not spaced:
            return _BETWEEN_THAI.sub("", text)
        text = " ".join(text.split())
        return _SPACE_AFTER_OPENING.sub("", _SPACE_BEFORE_CLOSING.sub("", text))

    stretch = [join(s).strip() for s in re.findall(r"\*([^*]+)\*", line)]
    return join(line), [s for s in stretch if s]


def check(lines: Iterable[str], lexicon: Checker) -> Coverage:
    tokens: list[Token] = []
    stretch: list[str] = []
    for line in lines:
        text, line_stretch = parse_line(line, lexicon.spaced)
        stretch.extend(line_stretch)
        tokens.extend(
            Token(piece, lexicon.status(piece)) for piece in lexicon.segment(text) if _counts(piece)
        )
    return Coverage(tuple(tokens), tuple(dict.fromkeys(stretch)))


def is_word(token: str) -> bool:
    """False for spaces and punctuation, which are shown but never counted or tapped."""
    return _counts(token)


def _counts(token: str) -> bool:
    return bool(token.strip()) and not _NOT_A_WORD.match(token)


def _is_number(token: str) -> bool:
    return bool(_NUMBER.match(token))
