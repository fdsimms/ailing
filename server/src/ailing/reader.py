"""A stored text as the app shows it: each line split into the pieces the server segmented, so a
tap always lands on something the lexicon or the gloss list knows about (docs/architecture.md,
Generation and coverage)."""

from typing import Any

from ailing import grammar
from ailing.coverage import Checker, is_word, parse_line
from ailing.store import StoredText


def gloss_for(
    word: str, glosses: dict[str, str], lexicon: Checker, meanings: dict[str, str]
) -> str | None:
    """The text's own gloss, else the deck's meaning (of the entry it's a form of, so hablé gets
    hablar's), else the meanings of the deck entries a known compound splits into (a word known
    that way has no entry of its own to gloss it)."""
    entry = lexicon.entry_of(word)
    if gloss := glosses.get(word) or meanings.get(word) or (meanings.get(entry) if entry else None):
        return gloss
    pieces = lexicon.known_pieces(word)
    parts = [meanings[p] for p in pieces or [] if p in meanings]
    return " + ".join(parts) if pieces and len(parts) == len(pieces) else None


def render(text: StoredText, lexicon: Checker, meanings: dict[str, str]) -> dict[str, Any]:
    stretch = set(text.stretch)
    practice = tuple(text.grammar.get("practice", []))
    avoid = tuple(text.grammar.get("avoid", []))
    lines = []
    for line in text.lines:
        plain, _ = parse_line(line.text, lexicon.spaced)
        # Which words use a practiced or avoided point, by index among the line's words.
        marked = grammar.marks(plain, lexicon, practice + avoid)
        at = 0
        words = []
        for piece in lexicon.segment(plain):
            if not is_word(piece):
                words.append(
                    {
                        "text": piece,
                        "status": None,
                        "gloss": None,
                        "stretch": False,
                        "deck": False,
                        "grammar": None,
                    }
                )
                continue
            covers = grammar.count_words(piece, lexicon.spaced)
            point = next((marked[i] for i in range(at, at + covers) if i in marked), None)
            at += covers
            entry = lexicon.entry_of(piece)
            words.append(
                {
                    "text": piece,
                    "status": lexicon.status(piece),
                    "gloss": gloss_for(piece, text.glosses, lexicon, meanings),
                    "stretch": (entry or piece) in stretch,
                    # A deck word, as against one known for being common (Spanish only).
                    "deck": entry is not None,
                    "grammar": point,
                }
            )
        lines.append({"speaker": line.speaker, "english": line.english, "words": words})
    return {
        "id": text.id,
        "topicId": text.topic_id,
        "title": text.title,
        "coverage": text.coverage,
        "stretch": list(text.stretch),
        "roles": text.roles,
        "form": text.form,
        "language": text.language,
        # The grammar this text was written to practice or avoid, for the reader's notes.
        "grammar": [
            {
                "id": pid,
                "name": grammar.POINTS[pid].name,
                "note": grammar.POINTS[pid].note,
                "role": role,
            }
            for role, ids in (("practice", practice), ("avoid", avoid))
            for pid in ids
            if pid in grammar.POINTS
        ],
        "lines": lines,
    }
