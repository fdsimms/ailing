"""The daily lexicon snapshot: every note's entry, meaning and tier in one language's deck, read from
Anki. Both decks use the Omnilanguage note type, so Entry and Meaning are read the same way.

Shapes and limits come from what the tools actually returned (docs/anki-spike.md). `cards_stats`
has no entry text or deck name, so cards are joined to notes by `nid`, and any card whose note
isn't in the Thai query (the Consonant Classes subdeck) is ignored.
"""

import html
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ailing.coverage import Checker, Lexicon
from ailing.gateway import AnkiUnavailable, CallTool
from ailing.languages import LANGUAGES, Code, Language
from ailing.spanish import SpanishLexicon
from ailing.tiers import Tier, note_tier

THAI_DECK = LANGUAGES["th"].deck
THAI_NOTES_QUERY = LANGUAGES["th"].notes_query

FIND_NOTES_PAGE = 500  # the tool's maximum
CARDS_STATS_PAGE = 1000  # the tool's maximum
NOTES_INFO_BATCH = 100

_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Entry:
    note_id: int
    text: str
    meaning: str
    tier: Tier
    due: bool = False  # a card of this note is due in Anki today


async def fetch_snapshot(call: CallTool, language: Language = LANGUAGES["th"]) -> list[Entry]:
    """Reads one language's deck. A reply that isn't the shape the spike recorded raises
    AnkiUnavailable, like an unreachable Anki, so the caller keeps yesterday's snapshot."""
    try:
        note_ids = await _all_note_ids(call, language.notes_query)
        notes = await _notes_info(call, note_ids)
        cards = await _all_cards(call, language.deck)
        return build_entries(notes, cards)
    except (KeyError, TypeError, AttributeError) as e:
        raise AnkiUnavailable(f"Anki's reply wasn't the expected shape: {e!r}") from e


def build_entries(notes: list[dict[str, Any]], cards: list[dict[str, Any]]) -> list[Entry]:
    cards_by_note: dict[int, list[tuple[int, int]]] = {}
    due_notes: set[int] = set()
    for card in cards:
        cards_by_note.setdefault(card["nid"], []).append((card["type"], card["ivl"]))
        if card.get("dueToday"):
            due_notes.add(card["nid"])

    entries = []
    for note in notes:
        fields = note["fields"]
        text = clean(fields.get("Entry", {}).get("value", ""))
        if not text:
            continue
        entries.append(
            Entry(
                note_id=note["noteId"],
                text=text,
                meaning=clean(fields.get("Meaning", {}).get("value", "")),
                tier=note_tier(cards_by_note.get(note["noteId"], [])),
                due=note["noteId"] in due_notes,
            )
        )
    return entries


def lexicon_from(entries: list[Entry], language: Code = "th") -> Checker:
    """Mature and young both count as known for coverage; unreviewed notes don't."""
    return _lexicon(language, frozenset(e.text for e in entries if e.tier != "unreviewed"))


@lru_cache(maxsize=4)
def _lexicon(language: Code, known: frozenset[str]) -> Checker:
    # Building one costs about a second (the segmenter's dictionary), so the same set of known
    # words reuses it: once per snapshot in production, once per test module in tests.
    return SpanishLexicon(known) if language == "es" else Lexicon(known)


def clean(value: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", value)).split())


async def _all_note_ids(call: CallTool, query: str) -> list[int]:
    ids: list[int] = []
    while True:
        page = await call(
            "find_notes", {"query": query, "limit": FIND_NOTES_PAGE, "offset": len(ids)}
        )
        ids.extend(page["noteIds"])
        if not page.get("hasMore") or not page["noteIds"]:
            return ids


async def _notes_info(call: CallTool, note_ids: list[int]) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for start in range(0, len(note_ids), NOTES_INFO_BATCH):
        batch = note_ids[start : start + NOTES_INFO_BATCH]
        result = await call("notes_info", {"notes": batch, "include_fields": ["Entry", "Meaning"]})
        notes.extend(result["notes"])
    return notes


async def _all_cards(call: CallTool, deck: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    while True:
        page = await call(
            "cards_stats", {"deck": deck, "limit": CARDS_STATS_PAGE, "offset": len(cards)}
        )
        cards.extend(page["cards"])
        if not page.get("hasMore") or not page["cards"]:
            return cards
