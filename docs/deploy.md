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
| `ANKIMCP_URL` | The full URL of the Anki proxy, `https://<hostname>/` (step 7); the add-on serves at `/`, not `/mcp` |
| `ANKIMCP_TOKEN` | The proxy's bearer token, the `ANKI_PROXY_TOKEN` made in step 7 |
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

## 4. Turn on backups

The reading log is what the Milestone 1 check reads, and Fly's own volume snapshots only last
about 5 days. Litestream streams every change to the database to Fly's object storage (Tigris)
and restores it by itself onto a new, empty volume.

```bash
fly storage create
```

Accept the defaults. It creates a bucket and sets its secrets on the app (`BUCKET_NAME`,
`AWS_ENDPOINT_URL_S3`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`; that list is
from memory, so check `fly secrets list` shows `BUCKET_NAME` afterwards). The server turns backups
on whenever `BUCKET_NAME` is set (`server/start.sh`), so there's nothing else to configure. Skipping
this step leaves the server running without backups.

## 5. Deploy

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

## 6. Redeploy after a change

Run `fly deploy` from `server/` again. The database and audio cache are on the volume, so they
survive a redeploy.

## 7. Anki proxy (on the droplet)

The Anki add-on's own tunnel (`tunnel.ankimcp.ai`) asks for an OAuth login that only Claude's
connector can do, so the Fly server can't use it. Instead, Caddy on the droplet puts HTTPS and a
bearer token in front of the add-on's local server (`127.0.0.1:3141/`). Port 3141 is never
exposed. The Claude connector's tunnel is untouched. Why: `docs/architecture.md`, Anki access.

Files: `proxy/Caddyfile.template` and `proxy/caddy-anki-proxy.conf`. Nothing secret is in the repo:
the hostname and the token live only in `/etc/caddy/anki-proxy.env` on the droplet.

Before starting: point a hostname at the droplet (an A record), or use `<ip-with-dashes>.sslip.io`
for a quick test only. Check the DigitalOcean dashboard for an existing cloud firewall: if there is
one, open 80 and 443 there instead of using `ufw`.

Run these on the droplet. Watch memory: `free -m` before and after.

**Install Caddy** (the official apt repository, from caddyserver.com/docs/install):

```bash
free -m
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
free -m
```

**Make the token and the env file.** `printf` is a shell builtin, so the token never appears in a
process list. The token is shown once, here; put it in your password manager. Copy only the 64
characters, and don't paste the terminal into a chat or a ticket: if the token shows up anywhere
it shouldn't, run these commands again to replace it. Before Caddy is started nothing else needs to
change; after, follow "Rotate the token" below.

```bash
sudo install -m 600 -o root -g root /dev/null /etc/caddy/anki-proxy.env
TOKEN=$(openssl rand -hex 32)
printf 'ANKI_PROXY_HOST=%s\nANKI_PROXY_TOKEN=%s\n' 'YOUR.HOSTNAME' "$TOKEN" | sudo tee /etc/caddy/anki-proxy.env >/dev/null
echo "$TOKEN"
unset TOKEN
```

**Install the config** (copy the two `proxy/` files to the droplet first, with `scp`):

```bash
sudo cp Caddyfile.template /etc/caddy/Caddyfile
sudo mkdir -p /etc/systemd/system/caddy.service.d
sudo cp caddy-anki-proxy.conf /etc/systemd/system/caddy.service.d/anki-proxy.conf
sudo systemctl daemon-reload
```

The drop-in makes Caddy refuse to start if the token is under 32 characters, because an empty one
would accept the header `Bearer `.

**Firewall.** Allow SSH first, and keep a second SSH session open until you've checked it.

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw default deny incoming
sudo ufw enable
ss -ltn | grep 3141    # must show 127.0.0.1:3141, never 0.0.0.0 or *
```

**Validate and start:**

```bash
sudo sh -c 'set -a; . /etc/caddy/anki-proxy.env; set +a; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile'
sudo systemctl restart caddy
systemctl status caddy --no-pager
```

Caddy asks Let's Encrypt for its certificate as soon as it starts, which needs the DNS record live
and ports 80 and 443 open. Give it a few seconds, then look for `certificate obtained successfully`
in `sudo journalctl -u caddy`.

**Test from your laptop.** `read -rs` keeps the token out of your shell history:

```bash
read -rs ANKI_TOKEN
HOST=https://YOUR.HOSTNAME/
curl -s -o /dev/null -w "%{http_code}\n" -X POST $HOST                                  # 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Authorization: Bearer wrong" $HOST   # 401
curl -s -X POST $HOST -H "Authorization: Bearer $ANKI_TOKEN" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

The last one should answer with the add-on's server info. If it fails with 403 or 421, look in
`journalctl -u caddy` and in the add-on's log: the add-on is rejecting the proxied Host or Origin.
The Caddyfile already rewrites Host and removes Origin, so say what the log shows before changing
anything else. Then check that Anki is unaffected: `journalctl -u anki` (or however it runs), the
Claude connector still answers, and `free -m` is similar to before.

**Point the Fly server at it:**

```bash
fly secrets set ANKIMCP_URL="https://YOUR.HOSTNAME/" ANKIMCP_TOKEN="..."
fly ssh console -C "python -m ailing.spike"
```

**Rotate the token:** make a new one as above (rewrite the `ANKI_PROXY_TOKEN` line in
`/etc/caddy/anki-proxy.env`), `sudo systemctl restart caddy`, then `fly secrets set ANKIMCP_TOKEN=...`.
Do it at once if the token ever appears anywhere it shouldn't.

**Check status:** `systemctl status caddy`, `journalctl -u caddy -n 50`.

**Roll back:** `sudo systemctl disable --now caddy`, then `sudo ufw delete allow 80/tcp` and
`sudo ufw delete allow 443/tcp`. Anki and the connector are unaffected.
