"""Spanish coverage: which words in a text are known (docs/architecture.md, Languages).

The Spanish deck holds advanced words (el blindaje, a quemarropa), not everyday ones, so the deck
alone can't be the dictionary the way it is for Thai. A word counts as known when it, or its lemma,
is one of the 10,000 most common Spanish words (data/es_common.txt) or a reviewed deck entry. The
owner chose this on 26 October 2026.

- Lemmas come from simplemma, so hablé, hablaríamos and hablaste all match hablar. It's loaded the
  first time Spanish is used (about 100 MB), so a Thai-only server doesn't pay for it.
- Pronouns joined to a verb (dámelo, sentarse) are taken off and the verb checked without its
  written accent.
- A deck entry with an article (el blindaje) is matched without it.
- A deck phrase (mantener a raya) is found by its lemmas, so mantuvimos a raya is one token, known,
  and counts as one word, like a Thai compound.
- Partial, as for Thai: a word that's neither common nor an entry but appears inside a deck phrase
  (quemarropa, from a quemarropa) counts as unknown, and its gloss can point at the phrase.
"""

import re
import unicodedata
from functools import cache, cached_property
from pathlib import Path
from typing import Any

from ailing.coverage import Status

_COMMON_FILE = Path(__file__).parent / "data" / "es_common.txt"
_ARTICLES = frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"})
# Pronouns that join onto the end of a verb, longest first, so "los" is tried before "lo".
_CLITICS = ("nos", "les", "los", "las", "me", "te", "se", "le", "lo", "la", "os")
_TOKEN = re.compile(r"\w+(?:['-]\w+)*|\s+|[^\w\s]", re.UNICODE)
_NUMBER = re.compile(r"^\d+([.,]\d+)*$")
_PHRASE_MAX = 6


@cache
def common_words() -> frozenset[str]:
    lines = _COMMON_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(w for w in lines if w and not w.startswith("#"))


@cache
def _lemmatizer() -> Any:
    import simplemma  # loaded on first use; see the module docstring

    return simplemma


@cache
def lemma(word: str) -> str:
    return str(_lemmatizer().lemmatize(word, lang="es")).lower()


def _plain(word: str) -> str:
    """Without written accents: dá → da. Keeps ñ and ü."""
    out = []
    for ch in unicodedata.normalize("NFD", word):
        if unicodedata.category(ch) == "Mn" and ch != "̃" and ch != "̈":
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def _is_word(token: str) -> bool:
    return any(ch.isalnum() for ch in token)


def _entry_key(entry: str) -> str:
    """A deck entry as it's matched: lowercased, without a leading article on a single word."""
    words = entry.lower().split()
    if len(words) == 2 and words[0] in _ARTICLES:
        return words[1]
    return " ".join(words)


class SpanishLexicon:
    spaced = True

    def __init__(self, known: list[str] | frozenset[str] | tuple[str, ...]) -> None:
        self.known = frozenset(e.strip() for e in known if e.strip())
        # key (word, or space-joined phrase) -> the deck entry as written
        self._entries: dict[str, str] = {}
        self._phrases: dict[tuple[str, ...], str] = {}
        self._phrase_words: set[str] = set()  # the words of deck phrases, as written
        for entry in sorted(self.known):
            key = _entry_key(entry)
            if " " in key:
                self._phrases[tuple(lemma(w) for w in key.split())] = entry
                self._phrases.setdefault(tuple(key.split()), entry)
                self._phrase_words.update(key.split())
                continue
            self._entries.setdefault(key, entry)
            self._entries.setdefault(lemma(key), entry)
            if re.search(r"[aei]rse$", key):
                # A reflexive verb (cerciorarse) also matches its forms without "se".
                self._entries.setdefault(key[:-2], entry)

    @cached_property
    def partial(self) -> frozenset[str]:
        """Words inside a deck phrase that aren't known on their own."""
        return frozenset(w for w in self._phrase_words if not self._is_known(w))

    # ==== Segmenting ====

    def segment(self, text: str) -> list[str]:
        """Words, spaces and punctuation, with a deck phrase's words joined into one token."""
        pieces = _TOKEN.findall(text)
        out: list[str] = []
        i = 0
        while i < len(pieces):
            match = self._phrase_at(pieces, i) if _is_word(pieces[i]) else None
            if match is not None:
                out.append("".join(pieces[i:match]))
                i = match
            else:
                out.append(pieces[i])
                i += 1
        return out

    def _phrase_at(self, pieces: list[str], start: int) -> int | None:
        """The end index of the longest deck phrase starting at `start`, if there is one."""
        words: list[str] = []
        ends: list[int] = []
        i = start
        while i < len(pieces) and len(words) < _PHRASE_MAX:
            piece = pieces[i]
            if _is_word(piece):
                words.append(piece.lower())
                ends.append(i + 1)
            elif not piece.isspace():
                break  # punctuation ends a phrase
            i += 1
        for n in range(len(words), 1, -1):
            surface = tuple(words[:n])
            if surface in self._phrases or tuple(lemma(w) for w in surface) in self._phrases:
                return ends[n - 1]
        return None

    # ==== Status ====

    def entry_of(self, token: str) -> str | None:
        words = tuple(token.lower().split())
        if len(words) > 1:
            return self._phrases.get(words) or self._phrases.get(tuple(lemma(w) for w in words))
        word = words[0] if words else ""
        for form in self._forms(word):
            if form in self._entries:
                return self._entries[form]
        return None

    def status(self, token: str) -> Status:
        if " " in token.strip():
            return "known" if self.entry_of(token) else "unknown"
        return self._word_status(token.lower())

    def _word_status(self, word: str) -> Status:
        if self._is_known(word):
            return "known"
        if word in self.partial or lemma(word) in self.partial:
            return "partial"
        return "unknown"

    def _is_known(self, word: str) -> bool:
        if _NUMBER.match(word):
            return True
        common = common_words()
        return any(form in common or form in self._entries for form in self._forms(word))

    def _forms(self, word: str) -> list[str]:
        """The word, its lemma, and the same for the verb under any joined pronouns."""
        forms = [word, lemma(word)]
        stem = word
        for _ in range(2):
            # At least two letters of verb must be left: dá from dámelo, but not from "le".
            clitic = next(
                (c for c in _CLITICS if stem.endswith(c) and len(stem) - len(c) >= 2), None
            )
            if clitic is None:
                break
            stem = stem[: -len(clitic)]
            bare = _plain(stem)
            forms += [bare, lemma(bare)]
        return forms

    def known_pieces(self, token: str) -> list[str] | None:
        return None  # no compounds to break down, as Thai has
