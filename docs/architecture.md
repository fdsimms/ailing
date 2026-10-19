# Architecture decisions

Decisions made after `docs/brief.md` was written, with the reason for each. Where this file and the
brief disagree, this file is newer.

## Kept from the brief

- **Python server.** Milestone 3's Spanish needs lemma matching, and the good tools for that are
  Python. PyThaiNLP alone would not justify it.
- **SQLite.** One user, light writes, one machine.
- **Anki over MCP.** The only way into the droplet. The server uses the Python `mcp` SDK as a plain
  client, with a 45-second timeout on every call.

## Client

- **An Expo / React Native iOS app** (`client/`), not the brief's home-screen web app. The owner
  chose this on 19 October 2026 to match dundundun. It uses the same Expo, React Native and
  TypeScript versions as dundundun, and the same test setup (Jest on pure logic, no component tests).
- Built with EAS and installed through TestFlight.
- Background audio is on (`UIBackgroundModes: audio`), so listening keeps going with the screen
  locked or in another app. That was the main thing a web app couldn't do well.
- The server's address is plain build config: `EXPO_PUBLIC_API_URL` in `client/eas.json`, inlined at
  build time. It has to match the Fly app's name (`server/fly.toml`). Nothing secret ships in the app.
- Three screens (login, topics, reader) switched by state in `App.tsx`, with no navigation library.
  The reader shows the server's word split as tappable words: a tap shows the gloss, and marking a
  word unknown is a second tap inside the gloss, so looking up a half-known word doesn't also flag it.
- Leaving a text by any route logs the reading once, rated or not, which takes it off the ready queue.

## Hosting

- **Fly.io**, as its own app, separate from the dundundun MCP app. Never on the Anki droplet.
- **One always-on machine** (512 MB, since PyThaiNLP is heavy). Small enough to cost a few dollars a
  month, and it means background work isn't cut off by the machine stopping.
- **No cron.** When the app is opened, the server refreshes the lexicon if the snapshot is over 24
  hours old, and tops up the queue of ready texts in the background.
- **Backups.** SQLite on a Fly volume, backed up continuously with Litestream to Tigris (Fly's
  S3-compatible storage). Fly's own volume snapshots only last about 5 days.
- **Login.** The app is public and holds paid API keys. One long passphrase, entered once in the
  app and kept in the iOS keychain (`expo-secure-store`), sent with every API call and checked on
  every API route.

## Lexicon

- A note's tier comes from its weakest reviewed card: **mature** if the lowest interval is 21 days or
  more, **young** if reviewed but below that, **unreviewed** if no card has been reviewed
  (`server/src/ailing/tiers.py`).
- Mature and young both count as known for coverage. The prompt asks the model to favor mature words.
- **Partial:** a word that only appears inside a longer deck entry (รับ inside รับอะไรดี). It counts as
  unknown for coverage, and its gloss can point at the entry it came from.
- Only the latest snapshot is kept. No history.

## Generation and coverage

- **The server re-segments every line.** The model's `|` breaks are not trusted for coverage: the
  server removes them, splits the line again with the lexicon-first segmenter, and computes coverage
  from that. The model's breaks are only a cross-check, and the asterisks still mark stretch words.
  The reader's tap targets come from the server's split.
- **Revise rather than regenerate.** A text under the 95% floor goes back to the model with the
  unknown words named ("replace ทอน, กลิ่น"). At most 3 attempts in total.
- **Model:** `claude-sonnet-5-5` at `medium` effort, with server-side refusal fallbacks
  (`fallbacks: "default"`). The owner chose Sonnet to start, at half Opus's price; revisit once real
  texts show whether its Thai holds up within the vocabulary. The reply is JSON held to a schema (`output_config.format`): a title,
  lines (speaker, `|`-split text, English), and glosses for words off the list. Revisions are
  appended to the same conversation, never edited, so the model's earlier thinking stays valid.
  `server/src/ailing/generator.py`.
- **A stretch word used fewer than 2 times** sends the text back too, even at full coverage.
- **Prompt caching.** The lexicon is the same on every call that day, so it sits in a cached prefix.
- **Glosses come with the text.** The model returns an English gloss for every word not in the
  lexicon in the same response, so tap-to-gloss never needs its own API call. Lexicon words use the
  deck's `Meaning`.
- **Stretch words** are 1-3 words due today or still young. No random assignment.

## Topics

- You keep a short list of favorite topics. The server keeps one ready text per favorite
  (`READY_PER_FAVORITE` in `engine.py`), topped up in the background after each request, so reading
  those never waits. A new topic, or a favorite whose text was just read, waits for one generation
  (about half a minute).
- A text leaves the queue once a reading is logged for it, rated or not, so the same text is never
  served twice.

## Server API

Every `/api` route needs the passphrase as `Authorization: Bearer <passphrase>`; with no
`APP_PASSPHRASE` set, they all refuse. `/health` is open. The routes are listed at the top of
`server/src/ailing/app.py`.

- A text comes back already split into words by the server, each with its status (known, partial,
  unknown, or none for punctuation), its gloss and whether it's a stretch word. The app never
  segments Thai itself.
- When something isn't set up yet (no API key, no word list), the route answers 503 with a sentence
  the app can show as is.
- The production app is built by `uvicorn --factory ailing.app:production_app`, so importing the
  module opens no database.

## Audio

- Azure neural voices, one per speaker: `th-TH-NiwatNeural` (male) for A and `th-TH-PremwadeeNeural`
  (female) for B. `AZURE_VOICE_A` and `AZURE_VOICE_B` override them without a code change. The voice
  names and the synthesis path weren't verifiable from the build sandbox (`server/src/ailing/tts.py`
  says which parts were), so the first real call is the check.
- Each line is spoken once at normal speed and cached as an MP3 on the volume
  (`AILING_AUDIO_DIR/<text>/<line>.mp3`). A new text gets its audio before it counts as ready; a line
  with no audio yet is made when it's first asked for, which covers texts written before the Azure
  key was set. An Azure failure leaves that line silent and never blocks the text.
- The 0.7x to 1.0x speed control is the player's rate with pitch kept (`expo-audio`), so there's one
  file per line whatever the speed. "Play" runs the dialogue line by line; each line has its own
  replay button. Playback continues with the ringer on silent and the screen locked.
- The app fetches audio itself, with the passphrase in the request's headers.
- The `expo-audio` plugin is configured with no microphone permission: the app never records.

## Logging

- Per text: date, language, mode, token count, verified coverage, stretch words, words glossed,
  words flagged unknown, rating, audio speed, listen-only or not, time spent.
- The rating adjusts the next text (too hard: coverage target up 1 point, one fewer stretch word;
  too easy: the reverse), within a 95% to 99% target and 1 to 3 stretch words
  (`server/src/ailing/difficulty.py`). The Milestone 1 exit check reads the log.
- Each text also records its model, tokens and cost in dollars, so the real cost per text can be
  read straight from the `texts` table.
- **Dropped:** the brief's randomized experiment (exposed versus held-back words, Anki outcome
  comparison, kill criterion). The owner decided on 19 October 2026 not to build it.

## Build order

1. Coverage checker, with re-segmenting (done)
2. Lexicon snapshot (done; the MCP client is tested against a local MCP server, and the real
   tunnel waits on its URL and credential, see `docs/anki-spike.md`)
3. Generator (done, tested against a scripted model; its first real call waits on the API key)
4. Reader and login (done; audio controls come with audio)
5. Audio (done; voices and the Azure call unverified until the first real call)
6. Deploy to Fly.io. The setup (`server/Dockerfile`, `server/fly.toml`, `docs/deploy.md`) came
   early, so the server can be live while the rest is built.
