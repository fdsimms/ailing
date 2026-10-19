# Anki spike notes

Status: **partial**. The three read tools were called through the AnkiMCP connector attached to this
Claude session, on 19 October 2026. That is *not* the spike the brief asks for: the brief wants a plain
MCP client in server code, with a 45-second timeout, and no Claude in the loop. That half is still
open (see "Still needed" below).

## What was run

- `list_decks`
- `find_notes` on the Thai deck, excluding the Consonant Classes subdeck
- `cards_stats` on the Thai deck
- `notes_info` on two notes

## Deck names

Emoji prefixes are part of the name. Do not strip them.

- Parent: `👅 Languages`
- Thai: `👅 Languages::🐘 ภาษาไทย` (deck id 1770346053823)
- Thai letter and tone cards: `👅 Languages::🐘 ภาษาไทย::🏛 Consonant Classes` (excluded from the lexicon)

## `find_notes`

Query used: `"deck:👅 Languages::🐘 ภาษาไทย" -"deck:👅 Languages::🐘 ภาษาไทย::🏛 Consonant Classes"`

- Matched 753 notes. (The brief's feasibility test used 785 studied notes. The two counts differ in
  what they include, so reconcile them when the snapshot job exists.)
- Returns `noteIds`, `count`, `total`, `hasMore`, `offset`, `limit`, plus a `message` and `hint`.
- With `include_first_field: true` it also returns `noteLabels`: `{noteId, firstField, truncated, fullLength}`.
  For this note type the first field is `Entry`, the Thai word.
- Paginated. Max 500 per call.

## `cards_stats`

Called with `deck: "👅 Languages::🐘 ภาษาไทย"`. Subdecks are included.

- `total` was 1913 cards (so the Consonant Classes cards are in there too, and each note has several cards).
- Each card is `{cid, nid, tags, type, queue, ivl, dueToday}`.
  - `type`: 0 new, 1 learning, 2 review, 3 relearning.
  - `queue`: -3/-2 buried, -1 suspended, 0 new, 1 learning, 2 review, 3 day-learning.
  - `ivl` is in days. Sample cards had 138 to 320.
- There is **no deck name and no entry text** on a card record. Join to notes through `nid`.
- Several cards share one `nid` (one note produces forward, reverse and audio cards). The lexicon needs
  a rule for the tier: the brief says "weight toward mature cards (interval of 21 days or more)", so
  the **minimum** interval across a note's reviewed cards decides the tier (a note is only as known as
  its weakest card). Decided on 19 October 2026 and implemented in `server/src/ailing/tiers.py`:
  mature is 21 days or more, young is reviewed but below that, unreviewed has no reviewed card.
- Paginated (limit 1000 max, ordered by card id).

## `notes_info`

Note type is `Omnilanguage`. It carries fields for every language, with most empty for Thai.

Fields the lexicon needs:

| Field | Example | Use |
|---|---|---|
| `Entry` | `ฉัน`, `เด็กผู้หญิง` | The word or phrase. Entries can be multi-word phrases. |
| `Meaning` | `I; me (feminine)` | English gloss. Can hold several senses separated by `;`. |
| `Context` | `ฉันชื่อนิดา` | Example sentence in Thai. |
| `ContextTranslation` | `My name is Nida.` | English for the example. |
| `Transliteration` | `chǎn` | Romanization. |
| `Language` | `thai` | Lowercase language key. Useful as a filter. |
| `PartOfSpeech` | `pronoun` | Also mirrored in `tags`. |
| `GenerateReverse` | `y` | Drill mode only. |
| `Classifier` | `คน` | Thai counter word. |
| `Audio` | `[sound:hypertts-….mp3]` | Existing audio. |

Other shape notes:

- Each field is `{value, order, description}`.
- A note lists its card ids in `cards`. The first note had three cards, and one id (1778429153678) is
  far from the other two, so it was probably added later (the audio card).
- Field values may contain HTML. Strip it before use.
- Pass `include_fields` to cut the response size. Without it, 28 fields come back per note.

## Not yet called

`get_card_memory_state`, `get_due_cards`, `present_card`, `rate_card`, `add_notes`. The first milestone
needs none of them. `rate_card` is the Milestone 2 spike.

## Still needed

To run the real spike from server code, I need:

1. The AnkiMCP endpoint URL (the ankimcp.ai tunnel).
2. Whatever credential it expects (token or header), supplied as an environment variable.
3. Outbound network access from wherever the spike runs to that host.

None of these are present in this environment, so nothing here was mocked.

## Decisions made after the spike

- **Hosting:** see `docs/architecture.md`.
