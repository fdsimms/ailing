"""Lexicon tiers. Rule: a note is only as known as its weakest reviewed card."""

from collections.abc import Iterable
from typing import Literal

Tier = Literal["mature", "young", "unreviewed"]

MATURE_INTERVAL_DAYS = 21
# Anki card types: 0 new, 1 learning, 2 review, 3 relearning.
_REVIEWED_TYPES = {1, 2, 3}


def note_tier(cards: Iterable[tuple[int, int]]) -> Tier:
    """Tier for one note from its cards as (type, interval in days) pairs."""
    intervals = [ivl for card_type, ivl in cards if card_type in _REVIEWED_TYPES]
    if not intervals:
        return "unreviewed"
    return "mature" if min(intervals) >= MATURE_INTERVAL_DAYS else "young"
