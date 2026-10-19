# Comprehensible Input Engine: Project Brief

Oct 18, 2026 · @Frankie Simms. Transcribed from the 12-page PDF brief. Evidence links are reduced to
citations; the full reference list is at the end.

## Summary

Rebuild the sentence drill prototype as a real app in a new repo, with three modes on one
Anki-connected core. The new piece is a **Read & Listen** mode: on-demand Thai dialogues and short
texts generated from the words already in Frankie's Anki deck, at about 95-98% known-word coverage.
Anki and FSRS stay the scheduler of record; this mode is ungraded input that never writes reviews
back.

- **Drill mode** (prototyped): graded sentence cards for due vocabulary, FSRS-scheduled.
- **Situations mode** (prototyped): scenario dialogues, outside FSRS.
- **Read & Listen mode** (prototyped as Reading, rebuilt here): coverage-checked reading and
  listening, with tap-to-gloss and a capped queue for mining new words into Anki.

Thai goes first, starting with dialogues. A test against the live deck put situational dialogues at
96-100% coverage. Spanish narrative reading is the second target.

The build moves to a repo worked on in Claude Code, because this mode needs a cached lexicon,
server-side Thai segmentation, TTS and an API key.

## App modes

The repo holds one app with three modes on a shared core. The September React prototype
(`sentence-drill.jsx`, built in the "Optimizing multiple language Anki decks" chat) is the working
spec. Copy it into the repo as `reference/` if the file still exists.

| Mode | What happens | Anki contact | Rating |
|---|---|---|---|
| Drill (prototype: Words) | Each due card gets a fresh sentence. Forward: read the target-language sentence, recall the meaning. Reverse: see English, produce the sentence. Each direction gets its own sentence so one never gives away the other. Reverse only for notes with GenerateReverse = y. | Reads due cards; writes grades back once verified (see below) | Binary: Got it / Missed it |
| Situations | Pick a scenario, language and 2-8 lines. "Them" lines are comprehension, "you" lines are production, in dialogue order. | None | Self-check only, never saved to FSRS |
| Read & Listen (prototype: Reading; the new CI mode) | Dialogues or short passages built from known words, with 1-3 stretch words (today's due words first). Audio, tap-to-gloss, coverage check. | Reads the lexicon only | One passage rating: too easy / about right / too hard |

### Shared core, carried over from the prototype

- **Token format:** the model returns each line as one string with `|` between words and stretch
  words in asterisks, e.g. `ฉัน|ต้องการ|*น้ำ*`. Nested JSON token arrays truncated responses, so they
  were dropped.
- **Tap to flag:** tapping any word marks it unknown. Captured words persist across sessions and
  feed the mining queue.
- **Structure flag:** one tap per item marks "the grammar here was unclear", separate from unknown
  words.
- **Batch and cache:** sentences are generated in batches ahead of time, never one live API call per
  card.
- **Paste mode:** a manual list of words not yet in Anki can drive Drill mode.
- **Deck names** include the emoji prefix, e.g. `👅 Languages::🐘 ภาษาไทย`.

**Grade write-back.** The prototype kept Drill grades in the session. AnkiMCP now has a `rate_card`
tool that takes a card id and rating, so Got it maps to Good (3) and Missed it to Again (1). Its
description requires `present_card` to reveal the answer first, so whether it works from an app is
the first thing to test. Until it does, Drill stays practice-only and real reviews stay in Anki.

**Already rejected, don't revisit:** cloze cards (context gives the answer away); saving generated
sentences as Anki cards at low retention targets; rescheduling Thai cards.

## Evidence base

The research supports high-coverage input for comprehension and consolidation, but not as the main
way to learn new words. Retrieval practice and word-focused work still do that job, which is why
Anki and Drill mode stay at the centre.

| Finding | Strength | Evidence |
|---|---|---|
| About 98% known words is the target for adequate reading without a dictionary, though not easy reading; 95% is a workable minimum. | Strong, replicated | Nation 2006, building on Hu & Nation 2000; Laufer & Ravenhorst-Kalovski 2010 |
| Coverage helps gradually, not as a cliff. Small vocabulary gains still raise comprehension. | Moderate | Laufer & Ravenhorst-Kalovski 2010 |
| Listening needs at least as much coverage. At 95%, comprehension was consistent; at 90%, it varied widely between people. Nation suggests speech may need more than 98% because it can't be reread. | Moderate | van Zeeland & Schmitt 2013, as reported in Schmitt et al.'s replication; Nation 2006 |
| Incidental learning from input is real but small: about 9-18% of target words on immediate tests, 6-17% delayed. | Strong, meta-analysis of 24 studies | Webb, Uchihara & Yanagisawa 2023 |
| More encounters help (r = .34). Spacing and engagement are among the moderators, though one extensive-reading study found no significant frequency effect. | Strong, meta-analysis of 26 studies; Webb & Chang 2015 dissents | Uchihara, Webb & Yanagisawa 2019 |
| Unprompted recall of new words from graded reading was rare after 3 months, even after several encounters. | Moderate, one study | Brown, Waring & Donkaewbua 2008 |
| Word-focused tasks taught more words than reading alone. Repeated retrieval beat repeated study for foreign vocabulary. | Strong | Laufer 2003; Karpicke & Roediger 2008 |
| Glosses raise learning from reading: 45% vs 27% of words on immediate tests. First-language glosses beat target-language ones; text, picture and audio glosses did equally well. | Strong, meta-analysis of 42 studies | Yanagisawa, Webb & Uchihara 2020 |
| Reading-while-listening matched reading for word learning and 72% of learners preferred it. Listening alone was much weaker in that study, though a meta-analysis found modes similar overall. | Mixed | Brown et al. 2008; Webb et al. 2023; Feng & Webb 2020 |
| Slower speech and learner control over rate and pausing help L2 listening comprehension. | Moderate | Zhao 1997 and Chaudron 1988, as reviewed in McBride 2007 |
| Training with several voices helps perception generalize to new speakers, but two voices did as well as six. | Mixed, small effect | Nagle, Bruun & Zárate-Sández 2025 |
| The best gap between reviews grows with how long you need to remember. | Strong, 317 experiments | Cepeda et al. 2006 |
| Interest in the topic increased word learning and led to more useful lookups. | Weak, one study | Cancino 2023 |
| Extensive reading has small-to-medium effects on reading proficiency, larger for adults and web-based material. | Strong, 49 studies | Jeon & Day 2016 |
| An LLM told to stay inside a 3,000-word list kept 97.3% of words in it; the rest went uncorrected. | Moderate, one study, older model | Park & Derakhshan 2026 |
| PyThaiNLP's default dictionary segmenter scored 71% on the BEST 2010 benchmark against about 96% for the best systems. | Moderate | Phatthiyaphaibun et al., citing Chormai et al. 2020 |

**Limits of this evidence.** Almost all of it comes from English as a second language, mostly
Japanese, Chinese and Taiwanese university students. None of it is about Thai or about a 15-year
multi-language learner. Krashen's "i+1" is a hypothesis, not a measured threshold; what the data
supports is that high coverage enables comprehension, and comprehension enables some incidental
learning.

## Design principles

Each rule traces to a row in the evidence table; the two marked *personal* come from Frankie's own
constraints.

1. **Anki and Drill teach words; Read & Listen consolidates them.** Retrieval and word-focused tasks
   beat reading for learning new words, and incidental pickup averages 9-18% of target words. Don't
   sell this mode as a replacement for reviews.
2. **Coverage floor 95%, target 98%.** Texts below 95% known words are regenerated, not shown.
   Listen-first texts aim for 98% or higher, since speech can't be reread.
3. **What counts as known:** a word studied in a review card counts; a word that only appears inside
   a studied phrase (รับ inside รับอะไรดี) counts as partial and is treated as unknown for coverage.
   Weight word choice toward mature cards (interval of 21 days or more) using `cards_stats`.
4. **1-3 stretch words per text, today's due or young words first.** Each appears 2-3 times in the
   text and comes back in later texts on later days. Repetition and spacing are both moderators of
   incidental learning.
5. **Gloss in English, on tap.** Stretch words carry an English gloss; any other word reveals one on
   tap. First-language glosses beat target-language ones.
6. **Read-while-listening is the default.** Text plus audio line by line, with speed from 0.7x to
   1.0x and replay per line. Listen-only unlocks for a text once it's rated "about right".
7. **Two voices.** Use different Thai TTS voices for the two speakers in a dialogue. The benefit is
   small and mixed, but it costs nothing.
8. **Generate, then verify in code.** The model proposes text with `|` word boundaries; the server
   checks coverage with a lexicon-first segmenter and rejects texts that miss the floor. Models
   don't reliably hold vocabulary limits on their own.
9. **Never grade FSRS from exposure.** Recognizing a word in a story isn't a recall test, and
   feeding it to FSRS would corrupt tuned intervals.
10. **Let Frankie pick the topic.** Scenario and topic choice stay in the user's hands, since
    interest raises learning.
11. **Adapt from the passage rating.** "Too hard" raises the coverage target and cuts stretch words
    for the next text; "too easy" does the reverse.
12. **Cap mining** (*personal*). Tapped words go to a review queue, and at most a set number per day
    go to Anki after Frankie approves them, to protect the ~300 reviews/day ceiling.
13. **No new review load** (*personal*). Nothing this mode does creates Anki cards or reviews
    without an explicit approval step.

## Architecture

The app server talks to Anki only through one gateway, and only lightly: a lexicon snapshot once a
day, plus Drill's due cards and grades. Everything else runs from the cached lexicon.

```
Anki droplet (1 GB, already swaps under load)
  AnkiMCP via ankimcp.ai  <->  Anki + FSRS (owns scheduling)

App server (separate host)
  Anki gateway (MCP client, 45 s timeout)
    -> 1 pull/day -> Lexicon snapshot (mature, young, partial)
    -> Generator (Claude API, |-split lines)  <-> Coverage checker (lexicon-first, 95% floor; under 95%: retry)
    -> pass -> TTS + audio cache (two Thai voices, 0.7-1.0x)
  Session log (ratings, taps, mining queue)

Phone (web app)
  Drill (due cards)  <-> gateway: cards
  Situations (scenarios)  <- generator: dialogues
  Read & Listen (audio + glosses)  <- TTS: texts ; -> session log: ratings, taps
```

Approved mined words (milestone 3) also go out through the gateway. Keep the app server off the 1 GB
droplet, which already swaps under load.

- **Server:** Python, because PyThaiNLP is Python; FastAPI is a reasonable default. SQLite for the
  lexicon, texts, audio index and logs.
- **Client:** a mobile-first web app (React + TypeScript) installable on the phone's home screen.
- **Anki gateway:** every call gets a 45-second timeout, because the tunnel hangs rather than errors
  when Anki is unreachable. If the tunnel is down, the app keeps working from yesterday's snapshot.
- **Generation:** batch texts ahead of time and cache them, so reading never waits on the API.
- **Secrets:** Claude API key and Azure Speech key in server environment variables, never the client.
- **Open question:** where the app server runs (a second small VPS, or a managed host).

## Thai feasibility test

Situational dialogues built from the Thai deck reached 96-100% coverage, so Thai can go first. The
test ran on 18 October 2026 against all 785 Thai notes that have been studied at least once (letter
and tone-rule cards excluded).

**Method.** Three texts were written by hand to stay close to the deck, then segmented with
PyThaiNLP (`newmm`). A token counted as known if it was a deck entry, a number, or split cleanly
into deck entries.

| Text | Known | Words outside the deck |
|---|---|---|
| Restaurant dialogue: ordering vegetarian, paying | 95.7% | ทอน, plus 3 false misses |
| Taxi dialogue: directions, meter, fare | 100% | none |
| Market trip narrative | 92.3% | กลิ่น, แทน, แรง, plus 1 false miss |

**Findings that change the build.**

- **The segmenter disagreed with the deck.** ข้าวเหนียว, รับ, เก็บ and ตุ๊กตุ๊ก were marked unknown only
  because the deck holds them inside longer entries (ข้าวเหนียวมะม่วง, รับอะไรดี, เก็บเงิน, รถตุ๊กตุ๊ก). The
  checker must load the lexicon as its dictionary and keep a "partial" tier.
- **Narrative drops faster than dialogue.** Description pulls in words the deck lacks, like "smell",
  "strong" and "instead". Start with dialogues and mini-scenes; add narrative as the deck grows.
- **"Studied once" overstates knowledge.** The test didn't filter by interval. The real lexicon needs
  maturity data from `cards_stats`.
- **The texts were hand-written, not generated.** Generated text under the same constraint still
  needs testing; that is the first milestone's job.

## Milestones

Milestone 1 is Thai Read & Listen working end to end on a phone, then two weeks of real use before
anything else is built. The prototype never got a real week of sessions, so validation comes before
features this time.

### Milestone 1: Thai Read & Listen

- [ ] Spike: connect to the AnkiMCP tunnel from server code as a plain MCP client, and confirm
      `find_notes`, `notes_info` and `cards_stats` work without Claude in the loop
- [ ] Lexicon snapshot: a daily job writes each Thai note's entry, meaning, note id, interval and
      tier (mature, young, partial) to a local file
- [ ] Coverage checker: lexicon-first segmentation with the partial tier, unit-tested on the three
      feasibility texts
- [ ] Generator: Claude API call with the lexicon and stretch words, returning `|`-split lines plus
      English glosses, with up to 3 regenerations when coverage misses the floor
- [ ] Reader: line by line, stretch words highlighted, tap for gloss, tap-to-flag, passage rating
- [ ] Audio: Thai neural TTS with two voices, speed control and per-line replay, cached per text.
      AnkiMCP's TTS tool already uses Azure neural voices, so an Azure Speech key may already exist
- [ ] Session log (see measurement plan)
- [ ] Exit check: 10 or more sessions over 2 weeks, median verified coverage of 95% or higher, most
      ratings "about right"

**Milestone 2: port Drill and Situations.** Bring both over from the prototype onto the shared core.
Drill writes grades back only if the `rate_card` spike succeeds.

**Milestone 3: mining and Spanish.** Tapped words become proposed Omnilanguage notes, approved one by
one, then added with `add_notes` and given audio, under the daily cap. Then Spanish, which needs
lemma matching for inflected forms.

**Out of scope for milestone 1:** grade write-back, adding anything to Anki, languages other than
Thai, offline mode, and any reimplementation of FSRS.

## Measurement plan

Treat the app as an experiment on one learner: randomize which words get extra exposure, then let
Anki's own review outcomes say whether it helped.

**Log per text:** date, language, mode, token count, verified coverage, stretch words, words
glossed, words flagged unknown, rating, audio speed, listen-only or not, and time spent.

**The comparison that matters.** Each day, take the eligible young words, randomly assign half to
appear as stretch words and hold the other half back. After a few weeks, compare their next Anki
review pass rates and FSRS retrievability (`get_card_memory_state`). Random assignment is what turns
"it feels useful" into evidence, because it removes the pull to pick words that were going to stick
anyway.

**Personal calibration.** Plot coverage against the passage rating to find Frankie's own comfortable
threshold. The 95-98% figures are group averages from other learners and languages.

**Kill criterion.** If held-out and exposed words show no difference after about 6 weeks, keep the
mode for listening practice and comprehension, and stop claiming it helps vocabulary.

## References

Brown, Waring & Donkaewbua (2008), *Reading in a Foreign Language* 20(2). Cancino (2023), *Learning
and Motivation* 83. Cepeda et al. (2006), *Psychological Bulletin* 132. Feng & Webb (2020), *Studies
in Second Language Acquisition* 42(3). Jeon & Day (2016), *Reading in a Foreign Language* 28(2).
Karpicke & Roediger (2008), *Science* 319. Laufer (2003), *Canadian Modern Language Review* 59(4).
Laufer & Ravenhorst-Kalovski (2010), *Reading in a Foreign Language* 22(1). McBride (2007), doctoral
dissertation, University of Arizona. Nagle, Bruun & Zárate-Sández (2025), *Applied Psycholinguistics*
46. Nation (2006), *Canadian Modern Language Review* 63(1). Park & Derakhshan (2026), *Language
Testing in Asia* 16. Phatthiyaphaibun et al., PyThaiNLP. Schmitt et al., replication of van Zeeland
& Schmitt (2012), Nation (2006), Cobb (2007), *Language Teaching*. Uchihara, Webb & Yanagisawa
(2019), *Language Learning* 69(3). Webb & Chang (2015), *Language Teaching Research* 19(6). Webb,
Uchihara & Yanagisawa (2023), *Language Teaching* 56(2). Yanagisawa, Webb & Uchihara (2020),
*Studies in Second Language Acquisition* 42(2).

Summaries in the original came from abstracts and linked pages; full texts were not available for
most. The PDF had the live links.
