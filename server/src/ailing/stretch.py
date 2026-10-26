"""Which words to stretch on: today's due words first, then young ones (docs/brief.md, design
principle 4). A mature word that's due counts, since it's being tested today; other mature words
don't need the push.

The same principle says a stretch word "comes back in later texts on later days", so a word that
was a stretch word in a text read on an earlier day goes ahead of both, until it has been one on
`RETURN_DAYS` different days. It still has to be due or young: a word that has matured since is
left alone.
"""

import random
from collections.abc import Mapping

from ailing.lexicon import Entry

RETURN_DAYS = 3


def pick_stretch(
    entries: list[Entry],
    count: int,
    rng: random.Random,
    practiced: Mapping[str, int] | None = None,
) -> list[Entry]:
    """`practiced` maps a word to the number of earlier days it was a stretch word in a text read."""
    practiced = practiced or {}
    candidates = [e for e in entries if (e.due and e.tier != "unreviewed") or e.tier == "young"]
    returning = [e for e in candidates if 0 < practiced.get(e.text, 0) < RETURN_DAYS]
    rest = [e for e in candidates if e not in returning]
    due = [e for e in rest if e.due]
    young = [e for e in rest if not e.due]
    rng.shuffle(returning)
    rng.shuffle(due)
    rng.shuffle(young)
    return (returning + due + young)[:count]
