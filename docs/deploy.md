# Deploying the server to Fly.io

How to run the Read & Listen server in the cloud, so the iOS app can reach it. It is its own Fly
app, separate from dundundun's MCP server, and never on the Anki droplet.

**Cost:** one always-on 512 MB machine plus a 1 GB volume, about $4 a month. Check
fly.io/docs/about/pricing for current numbers.

Every command runs from **`server/`**, where `fly.toml` and the `Dockerfile` live.

## 1. Log in

You already have flyctl from dundundun. If it's on another machine:

```bash
brew install flyctl
fly auth login
```

## 2. Create the app and its volume

App names are global. If `ailing` is taken, change `app` in `server/fly.toml` first and commit it.
`primary_region` is `ewr` (Secaucus, NJ), the same as dundundun's server.

```bash
cd server
fly apps create ailing
fly volumes create ailing_data --size 1 --region ewr
```

Fly warns that one volume has no redundancy. Answer yes: SQLite can only live on one machine.

## 3. Set the secrets

Fly never shows a secret again once it's set, so keep each one in your password manager too.
The server starts without them, and each feature that needs one says so until it's there.

| Secret | What it is |
|---|---|
| `ANTHROPIC_API_KEY` | The Claude API key made for this app |
| `AZURE_SPEECH_KEY` | The Azure Speech key |
| `AZURE_SPEECH_REGION` | The Speech resource's region, like `eastus` |
| `ANKIMCP_URL` | The AnkiMCP endpoint the server connects to |
| `ANKIMCP_TOKEN` | The credential AnkiMCP expects (this name may change once we know how it authenticates) |
| `APP_PASSPHRASE` | Made up by you. You type it once in the app on your phone |

```bash
fly secrets set \
  ANTHROPIC_API_KEY="..." \
  AZURE_SPEECH_KEY="..." \
  AZURE_SPEECH_REGION="..." \
  ANKIMCP_URL="..." \
  ANKIMCP_TOKEN="..." \
  APP_PASSPHRASE="..."
```

Setting secrets on an app that's already running restarts it.

Optional, not secret: `AZURE_VOICE_A` and `AZURE_VOICE_B` change the two Thai voices (defaults
`th-TH-NiwatNeural` and `th-TH-PremwadeeNeural`). Set them with `fly secrets set` too, or under
`[env]` in `fly.toml`.

## 4. Deploy

```bash
fly deploy
```

Then open `https://ailing.fly.dev/health` (with your app name) in a browser. It should say
`{"status":"ok"}`.

Then check the server can reach Anki, which is the first thing everything else needs:

```bash
fly ssh console -C "python -m ailing.spike"
```

It calls `find_notes`, `notes_info` and `cards_stats` once, read-only, and prints a few Thai notes
and cards. "AnkiMCP didn't answer" with a reason means the URL, the token or the tunnel needs a
look before going further.

## 5. Redeploy after a change

Run `fly deploy` from `server/` again. The database and audio cache are on the volume, so they
survive a redeploy.
