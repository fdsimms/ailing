# CLAUDE.md

Guidance for Claude Code in this repo. Read `docs/brief.md` before designing anything: it is the
spec, with the evidence behind each rule. Where this file and the brief disagree, the brief wins
and this file is stale.

## What this is

A Thai-first comprehensible input engine, with three modes on one Anki-connected core: Drill,
Situations, and **Read & Listen** (the new mode, built first). Read & Listen generates dialogues and
short texts from words already in the owner's Anki deck, verifies coverage in code, and plays them
with audio and tap-to-gloss. Anki + FSRS stay the scheduler of record.

It is a separate app from dundundun (the owner's task app, `fdsimms/todo`). Their only connection
is optional and described in `docs/dundundun-tie-in.md`.

## Current scope

**Milestone 1 only:** Thai Read & Listen end to end on a phone, then two weeks of real use before
building anything else. Out of scope until the exit check passes: grade write-back, adding anything
to Anki, languages other than Thai, offline mode, reimplementing FSRS, Drill and Situations.

## Rules that must not be broken (from the brief's design principles)

- **Never grade FSRS from exposure.** Nothing in Read & Listen writes reviews.
- **Never create Anki cards or reviews without an explicit approval step.** Mining is capped per day
  (~300 reviews/day ceiling) and happens only after the owner approves each word.
- **Generate, then verify in code.** The model proposes text with `|` between words and stretch
  words in `*asterisks*`; the server checks coverage and rejects texts under the floor
  (95% floor, 98% target; listen-first aims for 98%+). Never trust the model to stay in vocabulary.
- **Token format is a `|`-split string per line.** Nested JSON token arrays truncated responses.
- **What counts as known:** a studied word counts; a word that appears only inside a studied phrase
  is "partial" and counts as unknown for coverage. The checker is lexicon-first (the lexicon is its
  dictionary), not PyThaiNLP's default dictionary, which scored 71% on BEST 2010.
- **1-3 stretch words per text**, today's due or young words first, English gloss on tap.
- **Batch and cache.** Never one live API call per card or per page view.
- **The owner picks the topic.**
- **Already rejected, don't revisit:** cloze cards; saving generated sentences as Anki cards at low
  retention targets; rescheduling Thai cards.

## Stack and architecture

- Server: Python (PyThaiNLP is Python), FastAPI as the default, SQLite for lexicon, texts, audio
  index and logs. Client: mobile-first React + TypeScript web app, installable on the home screen.
- All Anki traffic goes through **one gateway** (an MCP client to AnkiMCP via ankimcp.ai). **Every
  call has a 45-second timeout**, because the tunnel hangs rather than errors when Anki is
  unreachable. If it's down, the app runs from yesterday's snapshot.
- The Anki droplet is 1 GB and already swaps under load: never run the app server on it. Where the
  app server runs is an open question.
- The server reads Anki only for a once-a-day lexicon snapshot (and, later, Drill's due cards).
  Everything else runs from the cached lexicon.
- Secrets (Claude API key, Azure Speech key) live in server environment variables, never the client.
- Deck names include emoji prefixes, e.g. `👅 Languages::🐘 ภาษาไทย`. Don't strip them.

## Working in this repo

- Keep one verification command (e.g. `make verify` or `npm run verify`) that runs typecheck, tests
  and lint, and run it before every commit. Set it up in the first PR.
- Test the coverage checker against the three feasibility texts in the brief (95.7%, 100%, 92.3%
  known; the false misses are the test cases that matter).
- Prefer a small test for any rule above that can be enforced by one.
- Open a PR for each completed milestone item. Target `main`. Don't stack PRs on other PRs.
- If you find a bug or a design question outside the current task, ask before fixing, filing an
  issue, or leaving it. Don't bury it in a PR description.
- UI copy: plain and literal, American English, no em dashes.
- Verify any unfamiliar API from its docs rather than guessing. For the Anki side, call the real
  tools (`find_notes`, `notes_info`, `cards_stats`, `get_card_memory_state`, `rate_card`,
  `present_card`, `add_notes`) and record what they actually return.

## Logging

Each text logs: date, language, mode, token count, verified coverage, stretch words, words glossed,
words flagged unknown, rating, audio speed, listen-only or not, time spent. The rating drives the
next text's difficulty, and the Milestone 1 exit check reads the log.

The brief's randomized experiment (held-back words, kill criterion) was dropped by the owner. Don't
build it. Decisions made since the brief are in `docs/architecture.md`; read it with the brief.
