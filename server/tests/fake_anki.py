"""A stand-in for AnkiMCP, built from the response shapes recorded in docs/anki-spike.md."""

from typing import Any


def note(note_id: int, entry: str, meaning: str) -> dict[str, Any]:
    return {
        "noteId": note_id,
        "modelName": "Omnilanguage",
        "tags": [],
        "fields": {
            "Entry": {"value": entry, "order": 0, "description": ""},
            "Meaning": {"value": meaning, "order": 1, "description": ""},
        },
        "cards": [],
        "mod": 1788981959,
    }


def card(nid: int, card_type: int, ivl: int, due: bool = False) -> dict[str, Any]:
    return {
        "cid": nid * 10,
        "nid": nid,
        "tags": [],
        "type": card_type,
        "queue": 2,
        "ivl": ivl,
        "dueToday": due,
    }


class FakeAnki:
    def __init__(self, notes: list[dict[str, Any]], cards: list[dict[str, Any]]) -> None:
        self.notes = {n["noteId"]: n for n in notes}
        self.cards = cards
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, args))
        if name == "find_notes":
            ids = list(self.notes)
            return _page(ids, args, "noteIds")
        if name == "notes_info":
            return {"notes": [self.notes[i] for i in args["notes"]]}
        if name == "cards_stats":
            return _page(self.cards, args, "cards")
        raise ValueError(f"unexpected tool {name}")


def _page(items: list[Any], args: dict[str, Any], key: str) -> dict[str, Any]:
    offset, limit = args.get("offset", 0), args["limit"]
    chunk = items[offset : offset + limit]
    return {
        key: chunk,
        "count": len(chunk),
        "total": len(items),
        "hasMore": offset + limit < len(items),
    }
