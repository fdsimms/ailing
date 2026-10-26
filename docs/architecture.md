# Architecture decisions

Decisions made after `docs/brief.md` was written, with the reason for each. Where this file and the
brief disagree, this file is newer.

## Kept from the brief

- **Python server.** Milestone 3's Spanish needs lemma matching, and the good tools for that are
  Python. PyThaiNLP alone would not justify it.
- **SQLite.** One user, light writes, one machine.
- **Anki over MCP.** The only way into the droplet. The server uses the Python `mcp` SDK as a plain
  client, with a 45-second timeout on every call.

## Anki access

- **Caddy on the droplet, not the add-on's tunnel.** The tunnel (`tunnel.ankimcp.ai`) does its own
  OAuth login and ignores the add-on's `http_api_key`, and the docs describe no token a script can
  use: the server got "Invalid or expired token" with a made-up one (24 October 2026). So Caddy
  terminates HTTPS on a hostname, forwards only requests with `Authorization: Bearer <token>` to
  `127.0.0.1:3141`, and answers 401 to the rest. Port 3141 stays on loopback; the firewall allows
  only 22, 80 and 443. The Claude connector still uses the tunnel.
- **What the token guards.** AnkiMCP includes `delete_notes` and `rate_card`, so a leaked token
  reaches the whole collection. It is 32 random bytes, kept only in a root-owned env file on the
  droplet and as a Fly secret, and Caddy won't start with a short or empty one. The server itself
  only reads (Milestone 1).
- Caddy adds little memory on the 1 GB droplet. Setup, rotation and rollback: `docs/deploy.md`, step 7.

## Client

- **An Expo / React Native iOS app** (`client/`), not the brief's home-screen web app. The owner
  chose this on 19 October 2026 to match dundundun. It uses the same Expo, React Native and
  TypeScript versions as dundundun, and the same test setup (Jest on pure logic, no component tests).
- Built with EAS and installed through TestFlight.
- Background audio is on (`UIBackgroundModes: audio`), so listening keeps going with the screen
  locked or in another app. That was the main thing a web app couldn't do well.
- The server's address is plain build config: `EXPO_PUBLIC_API_URL` in `client/eas.json`, inlined at
  build time. It has to match the Fly app's name (`server/fly.toml`). Nothing secret ships in the app.
- Five screens (login, topics, reader, past texts, marked words) switched by state in `App.tsx`,
  with no navigation library. The reader shows the server's word split as tappable words: a tap shows the
  gloss, and marking a word unknown is a second tap inside the gloss, so looking up a half-known
  word doesn't also flag it.
- Each line has an EN button that shows that line's English alone, so checking one line doesn't
  give away the rest. "Show English" still shows them all.
- **Listen only** (brief, design principle 6). Once a text is rated "About right", the end view
  offers to play it again with the Thai hidden; the lines show who's speaking instead, and "Show the
  text" brings the words back. The reading is then logged with `listen_only` true. The brief's
  "unlocks for a text" is read as "for the text just rated", since a text is never served twice.
- While audio plays, the text scrolls to keep the line being spoken in view.
- **Repeat line** in the player plays the current line over and over, for shadowing, until it's
  turned off.
- **Past texts**: texts read to the end, newest first (the last 50), opened in the same reader to
  read or listen to again. Reading one again isn't logged: the log is one row per text, and a reread
  shouldn't count toward the exit check or move difficulty. So there's no Done or rating, and words
  can be looked up but not marked unknown. One rated "About right" can be played listen-only straight
  away, since that's when the brief unlocks it.
- The reader's playback speed and the highlight switch are kept between launches, in the keychain
  next to the passphrase (`client/src/savedPrefs.ts`), so no new native module was needed.
- **Progress** on the topics screen: finished texts over the last 14 days against the Milestone 1
  exit check (10 texts, median coverage 95% or more, most rated "about right"), and the coverage
  target and practice word count new texts are written at, so the effect of a rating is visible.
  Only finished readings count.
- **Marked words**: every word marked unknown in a reading, newest first, with its gloss and whether
  it's in the deck, so they can be added to Anki by hand. Read-only toward Anki. "Clear" hides a
  word until it's marked again (`cleared_words` table). This is the list Milestone 3's mining queue
  would start from.
- Finishing a text (tapping Done) logs the reading once, rated or not, which takes it off the ready
  queue. A text left before Done (Back, or closing the app) isn't logged, so it's served again next
  time instead of a new one being written. A listen-only pass comes after Done, so leaving it by
  any route still logs the reading as finished.
- When the server rejects the saved passphrase (it was changed), the app forgets it and asks again.
  Topics also has a Log out.

## Hosting

- **Fly.io**, as its own app, separate from the dundundun MCP app. Never on the Anki droplet.
- **One always-on machine** (512 MB, since PyThaiNLP is heavy). Small enough to cost a few dollars a
  month, and it means background work isn't cut off by the machine stopping.
- **No cron.** When the app is opened, the server refreshes the lexicon if the snapshot is over 24
  hours old, and tops up the queue of ready texts in the background.
- **Backups.** SQLite on a Fly volume, backed up continuously with Litestream (v0.5.17, copied
  from its official image) to Tigris, Fly's S3-compatible storage. `server/start.sh` runs the
  server under `litestream replicate` whenever `BUCKET_NAME` is set (`fly storage create` sets
  it), restoring the database first if the volume is empty; without it, the server runs alone.
  Fly's own volume snapshots only last about 5 days.
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
  roles (who A and B are, like Waiter and Customer, shown above the lines in the reader), lines (speaker, `|`-split text, English), and glosses for words off the list. Revisions are
  appended to the same conversation, never edited, so the model's earlier thinking stays valid.
  `server/src/ailing/generator.py`.
- **A stretch word used fewer than 2 times** sends the text back too, even at full coverage.
- **Prompt caching.** The lexicon is the same on every call that day, so it sits in a cached prefix.
- **Glosses come with the text.** The model returns an English gloss for every word not in the
  lexicon in the same response, so tap-to-gloss never needs its own API call. Lexicon words use the
  deck's `Meaning`.
- **Stretch words** are 1-3 words due today or still young. No random assignment.
- **Stretch words come back on later days** (brief, design principle 4). A word that was a stretch
  word in a text read on an earlier day goes ahead of other due and young words, until it has been
  one on 3 different days (`RETURN_DAYS` in `server/src/ailing/stretch.py`). It still has to be due
  or young, so a word that has matured since is left alone. In "Fit the topic" it's offered first,
  and the model may still pass it over if it doesn't fit.
- **Dialogue length** is a setting: 6, 8 or 12 lines (`lines` in `/api/settings`), applying from the
  next text written. Longer dialogues have more room for unknown words before missing the floor.
- **The model chooses stretch words to fit the topic** (the default). It gets 15 due or young
  words and uses 1 to the current stretch count of them, so a dialogue about ordering food isn't
  bent around "tiger" because tiger happens to be due. The text records the ones it used. A text
  that uses none, too many, or one fewer than 2 times goes back for revision. The other setting,
  "Any due word", hands the model that many words to use, which keeps every due word in rotation at
  the cost of odder dialogues. It's a setting on the Topics screen (`GET`/`PATCH /api/settings`),
  stored on the server so background writes follow it, and like ratings it applies from the next
  text written. It's separate from difficulty on purpose: ratings decide how many stretch words and
  how much coverage; this decides only which words.

## Topics

- You keep a short list of favorite topics. The server keeps one ready text per favorite
  (`READY_PER_FAVORITE` in `engine.py`), topped up in the background after each request, so reading
  those never waits. A new topic, or a favorite whose text was just read, waits for one generation
  (about half a minute).
- **A text is written in the background, never inside a request.** Three attempts and the audio
  can take longer than an iPhone waits on one request, so `/next` answers 202 while a text is being
  written and the app asks again every few seconds. One write per topic at a time; a request that
  arrives while one is running waits for it rather than starting a second.
- **A failed write is reported once and then cools down.** The next request for that topic gets
  the reason (503 with a sentence). Asking again after that is a deliberate retry. The background
  top-up skips that topic for 30 minutes (`FAILURE_COOLDOWN`) and carries on with the others, so a
  topic that keeps missing the floor doesn't keep spending. Each topic reports its state (`ready`,
  `writing`, `failed`, `idle`) for the app to show.
- A text is stored as `pending` until its audio is made, then `ready`; one left pending by a
  restart is made ready at startup. A text that missed the floor is stored as `dropped`, never
  served, so its cost is still on record.
- A text leaves the queue once a reading is logged for it, rated or not, so the same text is never
  served twice.
- **Removing a topic** (press and hold it) hides it from the list and the background top-up. It's
  a flag on the row, not a delete, since its texts and readings point at it. Adding a topic with the
  same name brings it back, with any text it still had ready.

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
  replay button. Playback continues with the ringer on silent and the screen locked; the player
  keeps the audio session active between lines, or iOS could suspend the app in the gap. A line
  whose audio fails to load is skipped with a note. Thai plays over other audio (a podcast keeps
  going), as the owner chose.
- The app fetches audio itself, with the passphrase in the request's headers.
- The `expo-audio` plugin is configured with no microphone permission: the app never records.

## Logging

- Per text: date, language, mode, token count, verified coverage, stretch words, words glossed,
  words flagged unknown, rating, audio speed, listen-only or not, time spent.
- The rating adjusts the difficulty of texts written after it (too hard: coverage target up 1
  point, one fewer stretch word; too easy: the reverse), within a 95% to 99% target and 1 to 3
  stretch words (`server/src/ailing/difficulty.py`). A text already waiting in a favorite's queue
  keeps the difficulty it was written at, so a rating shows up one text later; the owner chose that
  over discarding queued texts (19 October 2026). The Milestone 1 exit check reads the log.
- A reading posted twice for the same text (a retried request) is counted once.
- Each text also records the model that actually answered (a refusal fallback can change it), its
  tokens and its cost in dollars, dropped texts included, so the real cost per text can be read
  straight from the `texts` table.
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
