"""Text generator: Claude writes a short Thai dialogue from the deck's known words, the server checks
it, and anything under the coverage floor goes back for revision with the problem words named.

The rules this enforces come from docs/brief.md (design principles 2, 4, 5 and 8):
- coverage is measured by the server's own segmentation, never by the model's `|` breaks
- 1-3 stretch words, each used 2-3 times
- at most 3 attempts; a text that still misses the floor is returned as not passed, never shown

The revision loop is written against `Ask`, so it's tested without a key. `claude_ask` is the real
call: the lexicon sits in a cached system prompt, and each revision is appended to the same
conversation (append-only, so the model's thinking stays valid across turns).
"""

import json
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal, cast

import anthropic
from anthropic.types.beta import BetaMessageParam, BetaOutputConfigParam, BetaTextBlockParam

from ailing.coverage import FLOOR, Coverage, Lexicon, check
from ailing.lexicon import Entry

MODEL = "claude-sonnet-5-5"
EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
MAX_TOKENS = 16000
MAX_ATTEMPTS = 3
MAX_STRETCH = 3
STRETCH_MIN_USES = 2

# Sent as a list of message dicts; returns the parsed draft and the assistant content to append.
Ask = Callable[[list[dict[str, Any]]], Coroutine[Any, Any, tuple[dict[str, Any], list[Any]]]]


class GenerationFailed(Exception):
    """The model refused, ran out of tokens, or returned something unusable."""


@dataclass(frozen=True)
class TextRequest:
    topic: str
    stretch: tuple[Entry, ...] = ()
    lines: int = 8
    floor: float = FLOOR

    def __post_init__(self) -> None:
        if len(self.stretch) > MAX_STRETCH:
            raise ValueError(f"At most {MAX_STRETCH} stretch words per text")


@dataclass(frozen=True)
class Line:
    speaker: str
    text: str  # as the model wrote it: `|` between words, stretch words in asterisks
    english: str


@dataclass(frozen=True)
class Generated:
    title: str
    lines: tuple[Line, ...]
    glosses: dict[str, str]
    coverage: Coverage
    attempts: int
    passed: bool
    missing_glosses: tuple[str, ...]


DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string", "enum": ["A", "B"]},
                    "text": {"type": "string"},
                    "english": {"type": "string"},
                },
                "required": ["speaker", "text", "english"],
                "additionalProperties": False,
            },
        },
        "glosses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"word": {"type": "string"}, "english": {"type": "string"}},
                "required": ["word", "english"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "lines", "glosses"],
    "additionalProperties": False,
}

_INSTRUCTIONS = """\
You write short Thai dialogues for one learner to read and listen to. They must be built almost \
entirely from words the learner already knows, which are listed below.

Rules:
- Use only words from the list. A word that appears only inside a longer list entry is not known \
on its own: รับ is not known just because รับอะไรดี is. Every word outside the list makes the text \
harder; the server measures this and sends back any text under the learner's coverage target.
- Prefer entries marked M (well known) over Y (still being learned).
- Write natural, everyday spoken Thai for the situation, between two speakers, A and B.
- In each line's text, put | between every word, and wrap each stretch word in asterisks every \
time it appears, like ฉัน|ต้องการ|*น้ำ*. Don't add spaces.
- Give "english", a natural English translation of each line.
- In "glosses", give a short English gloss for each stretch word and for every word you used that \
is not in the list.

Known words, one per line as: word | meaning | M or Y
"""


def system_prompt(entries: list[Entry]) -> str:
    """The stable, cached part of every request. Sorted by note id so it's byte-identical between
    calls on the same snapshot; anything that varies goes in the user message instead."""
    known = sorted((e for e in entries if e.tier != "unreviewed"), key=lambda e: e.note_id)
    words = "\n".join(
        f"{e.text} | {e.meaning} | {'M' if e.tier == 'mature' else 'Y'}" for e in known
    )
    return _INSTRUCTIONS + words


def request_message(request: TextRequest) -> str:
    parts = [
        f"Topic: {request.topic}",
        f"Write {request.lines} lines.",
        f"Coverage target: at least {request.floor:.0%} of words from the list.",
    ]
    if request.stretch:
        listed = "\n".join(f"- {e.text} ({e.meaning})" for e in request.stretch)
        parts.append(
            "Stretch words: use each of these 2 or 3 times, wrapped in asterisks:\n" + listed
        )
    else:
        parts.append("No stretch words this time.")
    return "\n".join(parts)


def revision_message(coverage: Coverage, short_stretch: list[str], floor: float) -> str:
    parts = [
        f"This draft is {coverage.ratio:.1%} known words; the target is at least {floor:.0%}."
        if coverage.ratio < floor
        else f"Coverage is fine ({coverage.ratio:.1%})."
    ]
    if unknown := coverage.words("unknown"):
        parts.append("These words are not in the list: " + ", ".join(unknown) + ".")
    if partial := coverage.words("partial"):
        parts.append(
            "These only appear inside longer list entries, so they don't count as known: "
            + ", ".join(partial)
            + "."
        )
    if short_stretch:
        parts.append(
            "These stretch words appear fewer than 2 times: " + ", ".join(short_stretch) + "."
        )
    parts.append(
        "Rewrite the whole dialogue on the same topic so it fixes this, replacing words with ones "
        "from the list. Return the full dialogue again in the same format."
    )
    return " ".join(parts)


async def generate(ask: Ask, lexicon: Lexicon, request: TextRequest) -> Generated:
    messages: list[dict[str, Any]] = [{"role": "user", "content": request_message(request)}]
    result: Generated | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        draft, content = await ask(messages)
        result, short_stretch = _assess(draft, lexicon, request, attempt)
        if result.passed:
            return result
        if attempt < MAX_ATTEMPTS:
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": revision_message(result.coverage, short_stretch, request.floor),
                }
            )
    assert result is not None
    return result


def _assess(
    draft: dict[str, Any], lexicon: Lexicon, request: TextRequest, attempt: int
) -> tuple[Generated, list[str]]:
    try:
        lines = tuple(Line(ln["speaker"], ln["text"], ln["english"]) for ln in draft["lines"])
        glosses = {g["word"]: g["english"] for g in draft["glosses"]}
        title = draft["title"]
    except (KeyError, TypeError) as e:
        raise GenerationFailed(f"The draft is missing a field: {e}") from e
    if not lines:
        raise GenerationFailed("The draft has no lines")

    coverage = check([ln.text for ln in lines], lexicon)
    uses = {e.text: sum(1 for t in coverage.tokens if t.text == e.text) for e in request.stretch}
    short_stretch = [word for word, n in uses.items() if n < STRETCH_MIN_USES]
    # Stretch words are glossed from the deck, so only off-list words need the model's gloss.
    for word in request.stretch:
        glosses.setdefault(word.text, word.meaning)
    missing = tuple(
        w for w in coverage.words("unknown") + coverage.words("partial") if w not in glosses
    )
    passed = coverage.meets(request.floor) and not short_stretch
    return Generated(title, lines, glosses, coverage, attempt, passed, missing), short_stretch


def claude_ask(client: anthropic.AsyncAnthropic, entries: list[Entry]) -> Ask:
    system: list[BetaTextBlockParam] = [
        {"type": "text", "text": system_prompt(entries), "cache_control": {"type": "ephemeral"}}
    ]
    output_config: BetaOutputConfigParam = {
        "effort": EFFORT,
        "format": {"type": "json_schema", "schema": DRAFT_SCHEMA},
    }

    async def ask(messages: list[dict[str, Any]]) -> tuple[dict[str, Any], list[Any]]:
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=cast(list[BetaMessageParam], messages),
            output_config=output_config,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise GenerationFailed("Claude declined to write this text")
        if response.stop_reason == "max_tokens":
            raise GenerationFailed("The response was cut off")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise GenerationFailed("The response had no text")
        try:
            draft = json.loads(text)
        except json.JSONDecodeError as e:
            raise GenerationFailed("The response wasn't valid JSON") from e
        return draft, list(response.content)

    return ask
