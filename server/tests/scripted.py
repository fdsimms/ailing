"""A scripted model and sample deck shared by the engine, reader and API tests."""

from typing import Any

from ailing.generator import Usage
from ailing.lexicon import Entry

ENTRIES = [
    Entry(1, "ฉัน", "I; me", "mature"),
    Entry(2, "อยาก", "want to", "mature"),
    Entry(3, "กิน", "eat", "mature"),
    Entry(4, "ข้าวเหนียวมะม่วง", "mango sticky rice", "young", due=True),
    Entry(5, "ครับ", "polite particle (male)", "mature"),
    Entry(6, "รับอะไรดี", "what would you like?", "mature"),
    Entry(7, "ทอน", "give change", "unreviewed"),
]


def draft(*texts: str, glosses: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "title": "At the stall",
        "roles": {"A": "Vendor", "B": "Customer"},
        "lines": [
            {"speaker": "AB"[i % 2], "text": t, "english": f"line {i}"} for i, t in enumerate(texts)
        ],
        "glosses": [{"word": w, "english": e} for w, e in (glosses or {}).items()],
    }


GOOD = draft("ฉัน|อยาก|กิน|*ข้าวเหนียวมะม่วง*|ครับ", "*ข้าวเหนียวมะม่วง*|ครับ!")
BAD = draft("ทอน|ทอน|ฉัน")


class ScriptedModel:
    """Returns the given drafts in order, then repeats the last one."""

    def __init__(self, *drafts: dict[str, Any]) -> None:
        self.drafts = list(drafts)
        self.calls = 0
        self.entries_seen: list[list[Entry]] = []

    def ask_for(self, entries: list[Entry]) -> Any:
        self.entries_seen.append(entries)

        async def ask(messages: list[dict[str, Any]]) -> tuple[dict[str, Any], list[Any], Usage]:
            self.calls += 1
            d = self.drafts.pop(0) if len(self.drafts) > 1 else self.drafts[0]
            return d, [{"type": "text", "text": "draft"}], Usage(100, 500, 2000, 0)

        return ask
