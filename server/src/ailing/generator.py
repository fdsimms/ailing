"""Text generator: Claude writes a short Thai dialogue or story from the deck's known words, the server checks
it, and anything under the coverage floor goes back for revision with the problem words named.

The rules this enforces come from docs/brief.md (design principles 2, 4, 5 and 8):
- coverage is measured by the server's own segmentation, never by the model's `|` breaks
- 1-3 stretch words, each used 2-3 times; when the model chooses them from a longer list, at least
  one and no more than it was asked for
- at most 3 attempts while a draft is under the floor; then the closest attempt is kept if it's at
  least MINIMUM (90%), and only a text under that is returned as not passed, never shown

The revision loop is written against `Ask`, so it's tested without a key. `claude_ask` is the real
call: the lexicon sits in a cached system prompt, and each revision is appended to the same
conversation (append-only, so the model's thinking stays valid across turns).
"""

import json
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

import anthropic
from anthropic.types.beta import BetaMessageParam, BetaOutputConfigParam, BetaTextBlockParam

from ailing import grammar
from ailing.coverage import FLOOR, MINIMUM, Checker, Coverage, check
from ailing.languages import Code
from ailing.lexicon import Entry

MODEL = "claude-sonnet-5-5"
EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "high"
MAX_TOKENS = 16000
MAX_ATTEMPTS = 3
MAX_STRETCH = 3
STRETCH_MIN_USES = 2

# Per million tokens: input, output, cache read, cache write (5-minute cache, 1.25x input). A model
# not listed here (a refusal fallback) is priced as MODEL, which is close enough for a running total.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-opus-4-8": (5.00, 25.00, 0.50, 6.25),
}


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str = ""  # the model that actually answered, which a refusal fallback can change

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
            other.model or self.model,
        )

    def cost_usd(self) -> float:
        inp, out, read, write = PRICES.get(self.model or MODEL, PRICES[MODEL])
        return (
            self.input_tokens * inp
            + self.output_tokens * out
            + self.cache_read_tokens * read
            + self.cache_write_tokens * write
        ) / 1_000_000


# Sent as a list of message dicts; returns the parsed draft, the assistant content to append, and
# the tokens the call used.
Ask = Callable[[list[dict[str, Any]]], Coroutine[Any, Any, tuple[dict[str, Any], list[Any], Usage]]]


class GenerationFailed(Exception):
    """The model refused, ran out of tokens, or returned something unusable."""


# A dialogue between A and B, or a short story told by a narrator (N), one sentence or two a line.
Form = Literal["dialogue", "story"]


@dataclass(frozen=True)
class TextRequest:
    topic: str
    # The stretch words to use, or with `choose` set, the words to choose them from: the model
    # picks 1 to `choose` of them that fit the topic, so a text about ordering food isn't bent
    # around "tiger" just because it's due.
    stretch: tuple[Entry, ...] = ()
    lines: int = 8
    floor: float = FLOOR
    choose: int | None = None
    form: Form = "dialogue"
    language: Code = "th"
    # Grammar point ids (grammar.py): used at least twice each, or kept out.
    practice: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        used = len(self.stretch) if self.choose is None else self.choose
        if used > MAX_STRETCH:
            raise ValueError(f"At most {MAX_STRETCH} stretch words per text")
        if self.choose is not None and (self.choose < 1 or not self.stretch):
            raise ValueError("Choosing stretch words needs at least one to choose and a list")


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
    passed: bool  # shown to the reader: it met the floor, or it's the closest attempt at MINIMUM+
    missing_glosses: tuple[str, ...]
    usage: Usage = Usage()
    stretch: tuple[str, ...] = ()  # the stretch words the text actually uses
    roles: dict[str, str] = field(default_factory=dict)  # speaker -> who they are, e.g. "Waiter"
    floor_met: bool = True  # False for a closest attempt kept under the floor
    # Uses of a practiced point short of the 2 asked for, plus uses of an avoided one. The
    # closest attempt kept under the rules can have some.
    grammar_problems: int = 0


DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "roles": {
            "type": "object",
            "properties": {"A": {"type": "string"}, "B": {"type": "string"}},
            "required": ["A", "B"],
            "additionalProperties": False,
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string", "enum": ["A", "B", "N"]},
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
    "required": ["title", "roles", "lines", "glosses"],
    "additionalProperties": False,
}

_INSTRUCTIONS = """\
You write short Thai texts for one learner to read and listen to: dialogues, or short stories. \
They must be built almost entirely from words the learner already knows, which are listed below.

Rules:
- Use only words from the list. A word that appears only inside a longer list entry is not known \
on its own: รับ is not known just because รับอะไรดี is. Every word outside the list makes the text \
harder; the server measures this and sends back any text under the learner's coverage target.
- Prefer entries marked M (well known) over Y (still being learned).
- Before you answer, go through your draft word by word and check each one is on the list. Replace \
any that isn't with a listed word or a simpler way of saying it. Getting this right first time \
matters more than a clever text.
- A dialogue is natural, everyday spoken Thai between two speakers, A and B. In "roles", say who \
A and B are in this situation, in one to three English words each, like "Waiter" and "Customer".
- A story is told by a narrator: every line's speaker is N, each line is one or two simple \
sentences, and the story has a beginning, something that happens, and an end. Keep the language \
plain, since description pulls in words the learner may not know. Leave both roles empty.
- In each line's text, put | between every word, and wrap each stretch word in asterisks every \
time it appears, like ฉัน|ต้องการ|*น้ำ*. Don't add spaces.
- Give "english", a natural English translation of each line.
- In "glosses", give a short English gloss for each stretch word and for every word you used that \
is not in the list.

Known words, one per line as: word | meaning | M or Y
"""

# Spanish counts the 10,000 most common words as known as well as the deck (spanish.py), and the
# deck holds advanced words, so the list is what to recycle rather than the only words allowed.
_SPANISH_INSTRUCTIONS = """\
You write short Spanish texts for one learner to read and listen to: dialogues, or short stories. \
Write Mexican Spanish: ustedes, never vosotros. The learner knows the 10,000 most common Spanish \
words, in all their forms, plus the words and phrases listed below, which are advanced words from \
their own flashcards.

Rules:
- Use common, everyday Spanish freely, along with words from the list. Every other word (anything \
rarer than the 10,000 most common words and not on the list) makes the text harder; the server \
measures this and sends back any text under the learner's coverage target. A word that appears \
only inside a longer list phrase is not known on its own: quemarropa is not known just because \
"a quemarropa" is.
- Before you answer, go through your draft word by word and check each one is either common or on \
the list. Replace any that isn't with a common word or a simpler way of saying it. Getting this \
right first time matters more than a clever text.
- A dialogue is natural, everyday spoken Spanish between two speakers, A and B. In "roles", say \
who A and B are in this situation, in one to three English words each, like "Waiter" and \
"Customer".
- A story is told by a narrator: every line's speaker is N, each line is one or two simple \
sentences, and the story has a beginning, something that happens, and an end. Leave both roles \
empty.
- In each line's text, put | between words instead of spaces, keep punctuation on its word, and \
wrap each stretch word or phrase in asterisks every time it appears, like \
¿Lograron|*mantener|a|raya*|al|enemigo? A stretch word can be inflected (*mantuvimos|a|raya*).
- Give "english", a natural English translation of each line.
- In "glosses", give a short English gloss for each stretch word and for every word you used that \
is neither common nor on the list.

The learner's flashcard words, one per line as: word | meaning | M (well known) or Y (still being \
learned)
"""

_PROMPTS: dict[Code, str] = {"th": _INSTRUCTIONS, "es": _SPANISH_INSTRUCTIONS}


def system_prompt(entries: list[Entry], language: Code = "th") -> str:
    """The stable, cached part of every request. Sorted by note id so it's byte-identical between
    calls on the same snapshot; anything that varies goes in the user message instead."""
    known = sorted((e for e in entries if e.tier != "unreviewed"), key=lambda e: e.note_id)
    words = "\n".join(
        f"{e.text} | {e.meaning} | {'M' if e.tier == 'mature' else 'Y'}" for e in known
    )
    return _PROMPTS[language] + words


def request_message(request: TextRequest) -> str:
    what = "a dialogue" if request.form == "dialogue" else "a short story"
    parts = [
        f"Topic: {request.topic}",
        f"Write {what} of {request.lines} lines.",
        f"Coverage target: at least {request.floor:.0%} of words from the list."
        if request.language == "th"
        else f"Coverage target: at least {request.floor:.0%} of words common or from the list.",
    ]
    listed = "\n".join(f"- {e.text} ({e.meaning})" for e in request.stretch)
    if request.choose is not None:
        how_many = "1" if request.choose == 1 else f"1 to {request.choose}"
        parts.append(
            f"Stretch words: pick {how_many} of these that fit the topic naturally, and use each "
            "one you pick 2 or 3 times, wrapped in asterisks. Leave the rest out:\n" + listed
        )
    elif request.stretch:
        parts.append(
            "Stretch words: use each of these 2 or 3 times, wrapped in asterisks:\n" + listed
        )
    else:
        parts.append("No stretch words this time.")
    if request.practice:
        parts.append(
            f"Grammar to practice: use each of these at least {grammar.PRACTICE_USES} times, "
            "where it fits naturally:\n" + _grammar_list(request.practice)
        )
    if request.avoid:
        parts.append(
            "Grammar to avoid: the learner hasn't learned these yet, so don't use them at all; "
            "say it another way:\n" + _grammar_list(request.avoid)
        )
    return "\n".join(parts)


def _grammar_list(point_ids: tuple[str, ...]) -> str:
    return "\n".join(f"- {grammar.POINTS[p].name} ({grammar.POINTS[p].note})" for p in point_ids)


def grammar_problems(
    lines: list[str], lexicon: Checker, request: TextRequest
) -> tuple[list[str], int]:
    """What's wrong with a draft's grammar, as sentences for the revision message, and how much:
    each use short of a practiced point, plus each use of an avoided one."""
    found = grammar.find_in_lines(lines, lexicon, request.practice + request.avoid)
    problems = []
    misses = 0
    for pid in request.practice:
        if (n := len(found[pid])) < grammar.PRACTICE_USES:
            misses += grammar.PRACTICE_USES - n
            problems.append(
                f"Use the {grammar.POINTS[pid].name} at least {grammar.PRACTICE_USES} times; "
                f"this draft uses it {n} {'time' if n == 1 else 'times'}."
            )
    for pid in request.avoid:
        if used := found[pid]:
            misses += len(used)
            problems.append(
                f"Don't use the {grammar.POINTS[pid].name}; this draft has: "
                + ", ".join(dict.fromkeys(used))
                + ". Say those another way."
            )
    return problems, misses


def revision_message(coverage: Coverage, problems: list[str], floor: float) -> str:
    """`problems` are the stretch word and grammar problems, as sentences."""
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
    parts.extend(problems)
    parts.append(
        "Rewrite the whole text on the same topic so it fixes this, replacing words with ones "
        "from the list. Return the full text again in the same format."
    )
    return " ".join(parts)


async def generate(ask: Ask, lexicon: Checker, request: TextRequest) -> Generated:
    messages: list[dict[str, Any]] = [{"role": "user", "content": request_message(request)}]
    result: Generated | None = None
    best: Generated | None = None  # the attempt with the highest coverage, the later one on a tie
    usage = Usage()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        draft, content, used = await ask(messages)
        usage += used
        result, problems = _assess(draft, lexicon, request, attempt)
        result = replace(result, usage=usage)
        if result.passed:
            return result
        # Fewer grammar problems first, then higher coverage; the later attempt on a tie.
        rank = (-result.grammar_problems, result.coverage.ratio)
        if best is None or rank >= (-best.grammar_problems, best.coverage.ratio):
            best = result
        if attempt < MAX_ATTEMPTS:
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": revision_message(result.coverage, problems, request.floor),
                }
            )
    assert result is not None and best is not None
    if best.coverage.ratio >= MINIMUM:
        # Every attempt missed (the floor, or only a stretch word rule): keep the closest one.
        return replace(
            best,
            passed=True,
            floor_met=best.coverage.meets(request.floor),
            attempts=result.attempts,
            usage=usage,
        )
    return result


def _assess(
    draft: dict[str, Any], lexicon: Checker, request: TextRequest, attempt: int
) -> tuple[Generated, list[str]]:
    try:
        lines = tuple(Line(ln["speaker"], ln["text"], ln["english"]) for ln in draft["lines"])
        glosses = {g["word"]: g["english"] for g in draft["glosses"]}
        title = draft["title"]
        roles = {k: str(v).strip() for k, v in draft.get("roles", {}).items() if str(v).strip()}
    except (KeyError, TypeError) as e:
        raise GenerationFailed(f"The draft is missing a field: {e}") from e
    if not lines:
        raise GenerationFailed("The draft has no lines")

    coverage = check([ln.text for ln in lines], lexicon)
    used, problems = _stretch_used(coverage, request, lexicon)
    grammar_issues, grammar_misses = grammar_problems([ln.text for ln in lines], lexicon, request)
    problems += grammar_issues
    # Stretch words are glossed from the deck, so only off-list words need the model's gloss.
    for word in used:
        glosses.setdefault(word.text, word.meaning)
    missing = tuple(
        w for w in coverage.words("unknown") + coverage.words("partial") if w not in glosses
    )
    passed = coverage.meets(request.floor) and not problems
    stretch = tuple(e.text for e in used)
    generated = Generated(
        title,
        lines,
        glosses,
        coverage,
        attempt,
        passed,
        missing,
        stretch=stretch,
        roles=roles,
        grammar_problems=grammar_misses,
    )
    return generated, problems


def _stretch_used(
    coverage: Coverage, request: TextRequest, lexicon: Checker
) -> tuple[list[Entry], list[str]]:
    """The stretch words the draft uses, and what's wrong with how it uses them, as sentences for
    the revision message. A chosen word is one of the offered words the draft put in asterisks."""
    if request.choose is None:
        used = list(request.stretch)
    else:
        # A marked word counts as the entry it's a form of: mantuvimos a raya as mantener a raya.
        marked = {lexicon.entry_of(w) or w for w in coverage.stretch_words}
        used = [e for e in request.stretch if e.text in marked]
    problems = []
    if request.choose is not None and not used:
        problems.append(
            "No stretch word from the list was used. Pick at least one and wrap it in asterisks."
        )
    if request.choose is not None and len(used) > request.choose:
        problems.append(
            f"Use at most {request.choose} stretch words; this draft uses "
            + ", ".join(e.text for e in used)
            + "."
        )
    uses = {
        e.text: sum(1 for t in coverage.tokens if (lexicon.entry_of(t.text) or t.text) == e.text)
        for e in used
    }
    if short := [word for word, n in uses.items() if n < STRETCH_MIN_USES]:
        problems.append("These stretch words appear fewer than 2 times: " + ", ".join(short) + ".")
    return used, problems


def claude_ask(
    client: anthropic.AsyncAnthropic, entries: list[Entry], language: Code = "th"
) -> Ask:
    system: list[BetaTextBlockParam] = [
        {
            "type": "text",
            "text": system_prompt(entries, language),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    output_config: BetaOutputConfigParam = {
        "effort": EFFORT,
        "format": {"type": "json_schema", "schema": DRAFT_SCHEMA},
    }

    async def ask(messages: list[dict[str, Any]]) -> tuple[dict[str, Any], list[Any], Usage]:
        try:
            response = await client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=cast(list[BetaMessageParam], messages),
                output_config=output_config,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as e:
            # Overloaded, rate limited, unreachable: say so rather than failing the request.
            raise GenerationFailed(f"Claude didn't answer ({type(e).__name__})") from e
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
        u = response.usage
        used = Usage(
            u.input_tokens,
            u.output_tokens,
            u.cache_read_input_tokens or 0,
            u.cache_creation_input_tokens or 0,
            response.model,
        )
        return draft, list(response.content), used

    return ask
