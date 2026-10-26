"""Grammar points the owner can practice or avoid (docs/architecture.md, Grammar). A practiced point
is asked for 2 or 3 times in each text; an avoided one is asked to be left out. Like coverage, the
server checks the draft rather than trusting the model, and a miss goes back for revision.

Each point has a finder: given a line's words, it returns the spans that use the point.

- Thai points are words (เคย, กำลัง, ที่สุด), matched on the checker's segmentation. The segmenter
  sometimes joins one onto the next word (กำลังกิน), so a word starting with the point counts too,
  except listed look-alikes: ต้องการ (want) isn't ต้อง (must).
- Spanish points are verb forms, found from their endings with simplemma confirming the word is
  a form of a verb, plus lists of irregular forms. This is close but not perfect: forms shared
  with another tense aren't counted (hablamos is "we speak" and "we spoke", so it counts as
  neither), and a rare irregular form can be missed.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from ailing.coverage import Checker, is_word, parse_line
from ailing.languages import Code

Span = tuple[int, int]  # word indices, end exclusive
Finder = Callable[[list[str]], list[Span]]

PRACTICE_USES = 2  # a practiced point appears at least this many times
MAX_PRACTICE = 2  # points practiced at once, so texts stay natural

_WORD = re.compile(r"\w+(?:['-]\w+)*", re.UNICODE)


@dataclass(frozen=True)
class Point:
    id: str
    language: Code
    name: str
    note: str  # what it means, with examples
    find: Finder


def words(plain: str, lexicon: Checker) -> list[str]:
    """A parsed line's words, in order, as the finders see them: Thai as segmented, Spanish
    lowercased and split on spaces and punctuation (a deck phrase's words are separate here)."""
    if lexicon.spaced:
        return [w.lower() for w in _WORD.findall(plain)]
    return [t for t in lexicon.segment(plain) if is_word(t)]


def count_words(token: str, spaced: bool) -> int:
    """How many of `words`' words a rendered token covers: a Spanish deck phrase covers several."""
    return len(_WORD.findall(token)) if spaced else 1


def find_in_lines(
    lines: list[str], lexicon: Checker, point_ids: tuple[str, ...]
) -> dict[str, list[str]]:
    """For each point, what it matched across the lines (model lines with `|` and asterisks), as
    the words of each match joined: {"es.pluperfect": ["había comido", "habían visto"]}."""
    found: dict[str, list[str]] = {pid: [] for pid in point_ids}
    for line in lines:
        plain, _ = parse_line(line, lexicon.spaced)
        ws = words(plain, lexicon)
        joiner = " " if lexicon.spaced else ""
        for pid in point_ids:
            found[pid] += [joiner.join(ws[a:b]) for a, b in POINTS[pid].find(ws)]
    return found


def marks(plain: str, lexicon: Checker, point_ids: tuple[str, ...]) -> dict[int, str]:
    """Which words of a line (by index in `words`) belong to which point, for the reader."""
    out: dict[int, str] = {}
    ws = words(plain, lexicon)
    for pid in point_ids:
        if pid not in POINTS:
            continue  # a point a text was written with that has since been removed
        for a, b in POINTS[pid].find(ws):
            for i in range(a, b):
                out.setdefault(i, pid)
    return out


# ==== Thai ====


def _thai(marker: str, *not_these: str) -> Finder:
    def find(ws: list[str]) -> list[Span]:
        return [
            (i, i + 1)
            for i, w in enumerate(ws)
            if w == marker or (w.startswith(marker) and not w.startswith(not_these or ("\0",)))
        ]

    return find


def _thai_any(*markers: str) -> Finder:
    finders = [_thai(m) for m in markers]
    return lambda ws: sorted({span for f in finders for span in f(ws)})


# ==== Spanish ====


def _lemma(word: str) -> str:
    from ailing.spanish import lemma  # loads simplemma, so only when Spanish is checked

    return lemma(word)


def _verb_lemma(word: str) -> str | None:
    """The infinitive this word is a conjugated form of, or None."""
    lem = _lemma(word)
    return lem if lem != word and lem.endswith(("ar", "er", "ir")) else None


def _each(test: Callable[[list[str], int], bool]) -> Finder:
    return lambda ws: [(i, i + 1) for i in range(len(ws)) if test(ws, i)]


_PARTICIPLE_IRREGULAR = frozenset(
    [
        "escrito",
        "visto",
        "hecho",
        "dicho",
        "puesto",
        "vuelto",
        "roto",
        "abierto",
        "muerto",
        "cubierto",
        "descubierto",
        "devuelto",
        "resuelto",
        "impreso",
        "satisfecho",
        "deshecho",
        "frito",
    ]
)


def _participle(word: str) -> bool:
    return word.endswith(("ado", "ido", "ído")) or word in _PARTICIPLE_IRREGULAR


def _after_aux(aux: frozenset[str]) -> Finder:
    def find(ws: list[str]) -> list[Span]:
        return [(i, i + 2) for i in range(len(ws) - 1) if ws[i] in aux and _participle(ws[i + 1])]

    return find


_HABER_PRESENT = frozenset({"he", "has", "ha", "hemos", "habéis", "han"})
_HABER_IMPERFECT = frozenset({"había", "habías", "habíamos", "habíais", "habían"})

_GERUND = re.compile(r"(ando|iendo|yendo|ándo\w+|iéndo\w+|yéndo\w+)$")


def _progressive(ws: list[str]) -> list[Span]:
    return [
        (i, i + 2)
        for i in range(len(ws) - 1)
        if _GERUND.search(ws[i + 1]) and _lemma(ws[i]) == "estar"
    ]


# Future and conditional are built on the infinitive (hablar-é) or one of these stems.
_IRREGULAR_STEMS = frozenset(
    [
        "tendr",
        "pondr",
        "saldr",
        "vendr",
        "valdr",
        "podr",
        "querr",
        "sabr",
        "cabr",
        "habr",
        "har",
        "dir",
        "ir",
    ]
)
_FUTURE_ENDINGS = ("emos", "éis", "ás", "án", "é", "á")
_CONDITIONAL_ENDINGS = ("íamos", "íais", "ías", "ían", "ía")


def _built_on_stem(word: str, endings: tuple[str, ...]) -> bool:
    for ending in endings:
        if word.endswith(ending):
            stem = word[: -len(ending)]
            return stem in _IRREGULAR_STEMS or (len(stem) > 2 and stem == _lemma(word))
    return False


def _future(ws: list[str], i: int) -> bool:
    return _built_on_stem(ws[i], _FUTURE_ENDINGS)


def _conditional(ws: list[str], i: int) -> bool:
    return _built_on_stem(ws[i], _CONDITIONAL_ENDINGS)


def _in_pluperfect(ws: list[str], i: int) -> bool:
    return ws[i] in _HABER_IMPERFECT and i + 1 < len(ws) and _participle(ws[i + 1])


_IMPERFECT_IRREGULAR = frozenset(
    [
        "era",
        "eras",
        "éramos",
        "erais",
        "eran",
        "iba",
        "ibas",
        "íbamos",
        "ibais",
        "iban",
        "veía",
        "veías",
        "veíamos",
        "veían",
    ]
)


def _imperfect(ws: list[str], i: int) -> bool:
    w = ws[i]
    if w in _IMPERFECT_IRREGULAR:
        return True
    if _in_pluperfect(ws, i) or _conditional(ws, i):
        return False
    lem = _verb_lemma(w)
    if lem is None:
        return False
    if lem.endswith("ar"):
        return w.endswith(("ábamos", "abais", "abas", "aban", "aba"))
    return w.endswith(_CONDITIONAL_ENDINGS)


_PRETERITE_IRREGULAR = frozenset(
    [
        "fui",
        "fuiste",
        "fue",
        "fuimos",
        "fuisteis",
        "fueron",
        "di",
        "diste",
        "dio",
        "dimos",
        "disteis",
        "dieron",
        "vi",
        "viste",
        "vio",
        "vimos",
        "vieron",
        "hubo",
        "dijeron",
        "trajeron",
        "condujeron",
        "produjeron",
    ]
)
# Strong preterites: tuv-e, hic-imos, quis-ieron. Not vin-o, which is also "wine".
_PRETERITE_STRONG = re.compile(
    r"^(tuv|estuv|anduv|pud|pus|quis|sup|vin|hic|hiz|dij|traj|conduj|produj|hub)"
    r"(e|o|imos|isteis|iste|ieron|eron)$"
)
_PRETERITE_ENDINGS = ("asteis", "aste", "aron", "isteis", "iste", "ieron", "ió", "ó", "é", "í")
_NOT_PRETERITE = frozenset({"esté", "dé", "sé", "vino"})


def _preterite(ws: list[str], i: int) -> bool:
    w = ws[i]
    if w in _NOT_PRETERITE:
        return False
    if w in _PRETERITE_IRREGULAR or _PRETERITE_STRONG.match(w):
        return True
    if _future(ws, i):
        return False
    return w.endswith(_PRETERITE_ENDINGS) and _verb_lemma(w) is not None


_SUBJUNCTIVE_IRREGULAR = frozenset(
    [
        "sea",
        "seas",
        "seamos",
        "sean",
        "vaya",
        "vayas",
        "vayamos",
        "vayan",
        "haya",
        "hayas",
        "hayamos",
        "hayan",
        "esté",
        "estés",
        "estemos",
        "estén",
        "dé",
        "des",
        "demos",
        "den",
        "sepa",
        "sepas",
        "sepamos",
        "sepan",
        "quepa",
        "quepas",
        "quepan",
    ]
)
# Indicative forms with subjunctive-looking endings: ir and haber.
_NOT_SUBJUNCTIVE = frozenset({"va", "vas", "van", "vamos", "ha", "has", "han"})
_IMPERFECT_SUBJUNCTIVE = re.compile(
    r"(áramos|arais|aras|aran|ara|ásemos|aseis|ases|asen|ase|"
    r"iéramos|ierais|ieras|ieran|iera|iésemos|ieseis|ieses|iesen|iese)$"
)
_IMPERFECT_SUBJUNCTIVE_IRREGULAR = re.compile(
    r"^(fu|dij|traj|conduj|produj)(eras|éramos|erais|eran|era|ese|eses|ésemos|esen)$"
)
# "fuera" alone is usually "outside"; "para" is a preposition.
_NOT_IMPERFECT_SUBJUNCTIVE = frozenset({"fuera", "para"})


def _imperfect_subjunctive(ws: list[str], i: int) -> bool:
    w = ws[i]
    if w in _NOT_IMPERFECT_SUBJUNCTIVE:
        return False
    if _IMPERFECT_SUBJUNCTIVE_IRREGULAR.match(w):
        return True
    return bool(_IMPERFECT_SUBJUNCTIVE.search(w)) and _verb_lemma(w) is not None


def _present_subjunctive(ws: list[str], i: int) -> bool:
    w = ws[i]
    if w in _SUBJUNCTIVE_IRREGULAR:
        return True
    if w in _NOT_SUBJUNCTIVE or w in _NOT_IMPERFECT_SUBJUNCTIVE or w in _HABER_IMPERFECT:
        return False
    if w.endswith(("ida", "idas", "ada", "adas") + _CONDITIONAL_ENDINGS):
        return False
    if _imperfect(ws, i) or _conditional(ws, i) or _imperfect_subjunctive(ws, i):
        return False
    lem = _verb_lemma(w)
    if lem is None:
        return False
    # The vowel swaps: -ar verbs take e (hable), -er and -ir verbs take a (coma, viva).
    if lem.endswith("ar"):
        return w.endswith(("emos", "éis", "es", "en", "e"))
    return w.endswith(("amos", "áis", "as", "an", "a"))


# ==== The points ====

_ALL = (
    Point(
        "es.preterite",
        "es",
        "Preterite",
        "Finished past events: hablé, comió, fueron",
        _each(_preterite),
    ),
    Point(
        "es.imperfect",
        "es",
        "Imperfect",
        "Ongoing or habitual past: hablaba, comía, era",
        _each(_imperfect),
    ),
    Point(
        "es.present_perfect",
        "es",
        "Present perfect",
        "Has done: he hablado, ha comido",
        _after_aux(_HABER_PRESENT),
    ),
    Point(
        "es.pluperfect",
        "es",
        "Pluperfect",
        "Had done: había hablado, habían comido",
        _after_aux(_HABER_IMPERFECT),
    ),
    Point("es.future", "es", "Future", "Will do: hablaré, tendrá, iremos", _each(_future)),
    Point(
        "es.conditional",
        "es",
        "Conditional",
        "Would do: hablaría, tendría, iríamos",
        _each(_conditional),
    ),
    Point(
        "es.progressive",
        "es",
        "Progressive",
        "Be doing: estoy hablando, estaba comiendo",
        _progressive,
    ),
    Point(
        "es.present_subjunctive",
        "es",
        "Present subjunctive",
        "quiero que vengas, ojalá llueva",
        _each(_present_subjunctive),
    ),
    Point(
        "es.imperfect_subjunctive",
        "es",
        "Imperfect subjunctive",
        "si tuviera tiempo, quería que vinieras",
        _each(_imperfect_subjunctive),
    ),
    Point("th.ever", "th", "เคย (have ever)", "Experience: เคยไป, have been", _thai("เคย")),
    Point(
        "th.ongoing", "th", "กำลัง (in the middle of)", "Ongoing: กำลังกิน, is eating", _thai("กำลัง")
    ),
    Point("th.future", "th", "จะ (will)", "Future or intention: จะไป, will go", _thai("จะ")),
    Point(
        "th.already", "th", "แล้ว (already, now)", "Done or changed: กินแล้ว, have eaten", _thai("แล้ว")
    ),
    Point(
        "th.must",
        "th",
        "ต้อง (must, have to)",
        "Obligation: ต้องไป, have to go",
        _thai("ต้อง", "ต้องการ"),
    ),
    Point(
        "th.comparison", "th", "กว่า (more than)", "Comparing: แพงกว่า, more expensive", _thai("กว่า")
    ),
    Point("th.superlative", "th", "ที่สุด (the most)", "Superlative: ดีที่สุด, the best", _thai("ที่สุด")),
    Point("th.if", "th", "ถ้า (if)", "Conditions: ถ้าฝนตก, if it rains", _thai("ถ้า")),
    Point("th.because", "th", "เพราะ (because)", "Reasons: เพราะว่า, because", _thai("เพราะ")),
    Point(
        "th.yes_no",
        "th",
        "ไหม, หรือเปล่า (yes or no questions)",
        "ไปไหม, are you going?",
        _thai_any("ไหม", "มั้ย", "หรือเปล่า"),
    ),
)

POINTS: dict[str, Point] = {p.id: p for p in _ALL}


def points_for(language: Code) -> list[Point]:
    return [p for p in _ALL if p.language == language]
