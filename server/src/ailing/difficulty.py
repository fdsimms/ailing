"""How hard the next text is, adjusted from the last rating (docs/brief.md, design principle 11):
"too hard" raises the coverage target and cuts a stretch word, "too easy" does the reverse.

The coverage target never drops below the 95% floor, and stretch words stay within 1 to 3.
"""

from dataclasses import dataclass, replace

from ailing.coverage import FLOOR

MAX_FLOOR = 0.99
FLOOR_STEP = 0.01
MIN_STRETCH = 1
MAX_STRETCH = 3

RATINGS = ("too_easy", "about_right", "too_hard")


@dataclass(frozen=True)
class Difficulty:
    floor: float = FLOOR
    stretch: int = 2


def adapt(current: Difficulty, rating: str | None) -> Difficulty:
    if rating == "too_hard":
        return replace(
            current,
            floor=round(min(MAX_FLOOR, current.floor + FLOOR_STEP), 2),
            stretch=max(MIN_STRETCH, current.stretch - 1),
        )
    if rating == "too_easy":
        return replace(
            current,
            floor=round(max(FLOOR, current.floor - FLOOR_STEP), 2),
            stretch=min(MAX_STRETCH, current.stretch + 1),
        )
    return current
