# dundundun tie-in (optional, build after the Milestone 1 exit check)

dundundun is the owner's task app (Expo/React Native, repo `fdsimms/todo`). This engine stays a
separate app. The two connect in two optional, independent ways. Neither changes the engine's core
rules: Anki and FSRS stay the scheduler, and nothing here creates Anki cards or reviews.

## 1. The engine completes a dundundun task (engine as an MCP client)

No dundundun app changes needed.

- dundundun has a project, **"Comprehensible Input Engine"** (id `mvebgtcg0i34hee`). Keep one daily
  task there titled **"Read & Listen (Thai)"**. It does not exist yet; create it when this is built.
- When a session finishes (a text read to the end, or rated), the engine calls `complete_task` on
  it. Find the task by title within that project (`search_tasks` / `list_tasks`).
- The engine never creates tasks. A missing task is logged and skipped.
- dundundun's MCP server is a remote HTTPS server. Writes need its write token, kept in the engine's
  server environment, never the client.
- dundundun's write tools use a preview-then-confirm flow (`preview_change`, then the write with
  `apply: true`, the `confirmToken` and the `willDo` lines). A background client has to handle that
  explicitly. Treat this as an open detail.

## 2. dundundun asks the engine (a generated task in dundundun)

Tracked as https://github.com/fdsimms/todo/issues/3893 (labels: explore, area:task-list,
model:sonnet, effort:medium). Modeled on dundundun's WaniKani generated task.

Engine exposes one read-only endpoint:

```
GET /api/dundundun/status?day=YYYY-MM-DD
Authorization: Bearer <token>

200 {"day": "YYYY-MM-DD", "ready": true, "doneToday": false, "sessionsToday": 0}
```

- `ready`: a cached text that passed the coverage floor exists for that day.
- `doneToday`: at least one text was finished that day.
- `day` is dundundun's logical day, sent by the app (its day starts at the user's reset time, 04:00,
  not midnight).
- No text, words, ratings or lexicon leave the engine. Version the contract by adding fields only.
- Auth: a static bearer token the owner pastes into dundundun's settings. dundundun stores it in the
  keychain and the URL in settings, both or neither, off by default behind its own switch.

## Not tied in on purpose

The session log, FSRS, the mining queue and the ~300 reviews/day cap stay in the engine and Anki.
