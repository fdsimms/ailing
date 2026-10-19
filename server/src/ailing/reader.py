"""A stored text as the app shows it: each line split into the pieces the server segmented, so a
tap always lands on something the lexicon or the gloss list knows about (docs/architecture.md,
Generation and coverage)."""

from typing import Any

from ailing.coverage import Lexicon, is_word, parse_line
from ailing.store import StoredText


def render(text: StoredText, lexicon: Lexicon, meanings: dict[str, str]) -> dict[str, Any]:
    stretch = set(text.stretch)

    def _compound(word: str) -> str | None:
        # A word known because it splits into deck entries has no entry of its own to gloss it.
        pieces = lexicon.known_pieces(word)
        glosses = [meanings[p] for p in pieces or [] if p in meanings]
        return " + ".join(glosses) if pieces and len(glosses) == len(pieces) else None

    lines = []
    for line in text.lines:
        plain, _ = parse_line(line.text)
        words = []
        for piece in lexicon.segment(plain):
            if not is_word(piece):
                words.append({"text": piece, "status": None, "gloss": None, "stretch": False})
                continue
            words.append(
                {
                    "text": piece,
                    "status": lexicon.status(piece),
                    "gloss": text.glosses.get(piece) or meanings.get(piece) or _compound(piece),
                    "stretch": piece in stretch,
                }
            )
        lines.append({"speaker": line.speaker, "english": line.english, "words": words})
    return {
        "id": text.id,
        "topicId": text.topic_id,
        "title": text.title,
        "coverage": text.coverage,
        "stretch": list(text.stretch),
        "lines": lines,
    }
