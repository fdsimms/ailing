"""The languages texts can be written in, and what differs between them (docs/architecture.md,
Languages): the Anki deck, the voices, how a line is written, and how known words are counted.

Thai counts only deck words as known, segmented with the deck as the dictionary (coverage.py).
Spanish counts the 10,000 most common Spanish words plus deck words, matched by lemma (spanish.py),
because the Spanish deck holds advanced words, not everyday ones.
"""

from dataclasses import dataclass, field
from typing import Literal

Code = Literal["th", "es"]


@dataclass(frozen=True)
class Language:
    code: Code
    name: str  # in English, as the prompt and the app say it
    deck: str
    notes_query: str
    voices: dict[str, str] = field(default_factory=dict)  # speaker -> Azure voice
    # Written with spaces between words. Thai isn't, so spaces the model adds there are dropped.
    spaced: bool = False


_THAI_DECK = "👅 Languages::🐘 ภาษาไทย"
_SPANISH_DECK = "👅 Languages::🌮 Español"

LANGUAGES: dict[Code, Language] = {
    "th": Language(
        code="th",
        name="Thai",
        deck=_THAI_DECK,
        notes_query=f'"deck:{_THAI_DECK}" -"deck:{_THAI_DECK}::🏛 Consonant Classes"',
        voices={"A": "th-TH-NiwatNeural", "B": "th-TH-PremwadeeNeural"},
    ),
    "es": Language(
        code="es",
        name="Spanish",
        deck=_SPANISH_DECK,
        notes_query=f'"deck:{_SPANISH_DECK}"',
        # Mexican Spanish, as the owner chose (26 October 2026).
        voices={"A": "es-MX-JorgeNeural", "B": "es-MX-DaliaNeural"},
        spaced=True,
    ),
}
