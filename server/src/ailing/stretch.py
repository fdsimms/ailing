"""Which words to stretch on: today's due words first, then young ones (docs/brief.md, design
principle 4). A mature word that's due counts, since it's being tested today; other mature words
don't need the push."""

import random

from ailing.lexicon import Entry


def pick_stretch(entries: list[Entry], count: int, rng: random.Random) -> list[Entry]:
    due = [e for e in entries if e.due and e.tier != "unreviewed"]
    young = [e for e in entries if e.tier == "young" and not e.due]
    rng.shuffle(due)
    rng.shuffle(young)
    return (due + young)[:count]
