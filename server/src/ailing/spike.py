"""The brief's first spike, as a command: call find_notes, notes_info and cards_stats on the Thai deck
through AnkiMCP, with no Claude in the loop, and print what came back.

    ANKIMCP_URL=... ANKIMCP_TOKEN=... uv run python -m ailing.spike

On Fly, after the secrets are set: `fly ssh console -C "python -m ailing.spike"`. Read-only: it
writes nothing to Anki and nothing to the database.
"""

import asyncio
import json
import os
import sys
from typing import Any

from ailing.ankimcp import ankimcp_call_tool
from ailing.gateway import AnkiUnavailable, CallTool
from ailing.lexicon import THAI_DECK, THAI_NOTES_QUERY


async def run(call: CallTool) -> None:
    found = await call("find_notes", {"query": THAI_NOTES_QUERY, "limit": 3, "offset": 0})
    print("find_notes:", _summary(found, "noteIds"))
    ids = found.get("noteIds", [])[:3]
    if ids:
        info = await call("notes_info", {"notes": ids, "include_fields": ["Entry", "Meaning"]})
        for note in info.get("notes", []):
            fields = note.get("fields", {})
            entry = fields.get("Entry", {}).get("value")
            meaning = fields.get("Meaning", {}).get("value")
            print(f"notes_info: {note.get('noteId')} {entry!r} = {meaning!r}")
    cards = await call("cards_stats", {"deck": THAI_DECK, "limit": 3, "offset": 0})
    print("cards_stats:", _summary(cards, "cards"))
    for card in cards.get("cards", []):
        print("  ", json.dumps(card, ensure_ascii=False))


def _summary(result: dict[str, Any], key: str) -> str:
    return f"total {result.get('total')}, keys {sorted(result)}, first {len(result.get(key, []))}"


def main() -> int:
    url = os.environ.get("ANKIMCP_URL")
    if not url:
        print("Set ANKIMCP_URL (and ANKIMCP_TOKEN if it needs one).", file=sys.stderr)
        return 2
    try:
        asyncio.run(run(ankimcp_call_tool(url, os.environ.get("ANKIMCP_TOKEN"))))
    except AnkiUnavailable as e:
        print(f"AnkiMCP didn't answer: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
