# Immich auto-update script — the two tag-parsing bugs + the current working script

Location on 50.1: `/boot/config/plugins/user.scripts/scripts/immich update/script`
(plugin runtime copy: `/tmp/user.scripts/tmpScripts/immich update/script`, overwritten each run;
Unraid logs each run to syslog: `emhttpd: cmd: /usr/local/emhttp/plugins/user.scripts/startScript.sh ...` —
that line is how you count/时间线 the runs when the plugin's `finished/`+`running/` dirs are empty).

App dir: `/mnt/user/appdata/immich` (`.env`, `docker-compose.yml`, version backups `docker-compose.yml.<ver>-bak`).
Env facts: `DB_DATA_LOCATION=/mnt/user/appdata/postgres`, `UPLOAD_LOCATION=/mnt/user/imch_photos` (184G),
web UI on `2283`, extra read-only photo mount `/mnt/user/NAS/Z5:/photos/Z5:ro` (re-added by the script).

## Bug 1 — v1 script: single-line JSON assumption (found 2026-09-11, v3.0.3→v3.1.0 case)

`LATEST=$(curl ... | grep '"tag_name"' | cut -d'"' -f4)` — with compact JSON the grep matched the
whole line, so `cut -f4` returned the API `url` → the following `sed -i` died on the slashes and the
`&&` chain aborted: compose backup written, `.env` NOT updated, images never pulled.

"Fix" applied then: `grep -o '"tag_name":"[^"]*"' | cut -d'"' -f4` + `[ -z "$LATEST" ]` guard.

## Bug 2 — v2 script: API now answers PRETTY-PRINTED JSON (found 2026-10-02, v3.2.0→v3.2.4 case)

Symptom the user sees in the plugin console:

```
ERROR: Could not determine latest version from GitHub API. Aborting.
```

Reproduced on 50.1 — the guard fires because the pattern can no longer match:

```
$ curl -sSL 'https://api.github.com/repos/immich-app/immich/releases/latest' -o /tmp/gh.json   # HTTP=200, 23300 bytes
$ wc -l < /tmp/gh.json            # 415      <- NOT single-line
$ grep -n tag_name /tmp/gh.json   #  29:  "tag_name": "v3.2.4",
$ grep -o '"tag_name":"[^"]*"' /tmp/gh.json; echo rc=$?    # rc=1, no output  <- v2 pattern dead
$ grep -oE '"tag_name": *"[^"]*"' /tmp/gh.json             # "tag_name": "v3.2.4"   <- tolerant pattern works
```

Rate limit was NOT the cause (`x-ratelimit-remaining: 57`) — don't chase that.
Both "/releases/latest returns one line" notes in the skill were wrong/stale; verify against the live body
before believing any grep you inherited.

### Robust extraction (two independent sources)

```bash
RAW=$(curl -sL --max-time 30 "https://api.github.com/repos/immich-app/immich/releases/latest")
LATEST=$(printf '%s\n' "$RAW" | sed -nE 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' | head -1)
[ -z "$LATEST" ] && LATEST=$(curl -sIL --max-time 30 \
  "https://github.com/immich-app/immich/releases/latest" | grep -i '^location:' | tail -1 \
  | sed -E 's#.*/tag/##' | tr -d '\r' | tr -d ' ')
```

The `sed -nE` form is shape-independent (verified on the live pretty body and on a synthetic compact
`{"tag_name":"v9.9.9"}` line). The redirect source needs no API token, no JSON parsing and is not
rate-limited; a 302 → `.../releases/tag/v3.2.4` means the tag is the last path segment.

## Half-applied runs (the trap after any abort)

The script edits `.env` + `docker-compose.yml` BEFORE pulling, so an aborted/killed run (user closes the
plugin window → "closing this window will abort the execution of this script") leaves:

| Check | Half-applied state seen 2026-10-02 |
|---|---|
| `grep IMMICH_VERSION .env` | `v3.2.4` (new) |
| `docker ps` / `docker images` | `v3.2.0` (old, no v3.2.4 image pulled) |
| `ls docker-compose.yml*` | `...v3.2.0-bak` created at the same second |

Re-running the fixed script is safe and completes the job (versions equal → "Already on" branch →
`pull` + `up -d`). Timeline forensics: syslog `emhttpd: cmd: .../startScript.sh` lines + file mtimes
(that's how the 19:00:54 and 19:04:29 runs were separated from the stale `finished/` marker dirs).

## Deploy ritual (what was actually done)

```bash
D="/boot/config/plugins/user.scripts/scripts/immich update"
cp "$D/script" "$D/script.bak-$(date +%Y%m%d-%H%M%S)"   # keep the previous version
cp script.new "$D/script" && chmod +x "$D/script" && bash -n "$D/script"
```

Sandbox test BEFORE deploying (stub `docker` so no real pull/up can fire; the compose project name is
`immich` from the compose `name:` field, so running it in a sandbox dir would otherwise recreate the REAL
containers):

```bash
mkdir -p /tmp/immich-sb/bin && printf '#!/bin/sh\necho "[STUB docker] $*"\nexit 0\n' > /tmp/immich-sb/bin/docker && chmod +x /tmp/immich-sb/bin/docker
# copy .env + compose into the sandbox, rewrite the script's cd line, then:
PATH=/tmp/immich-sb/bin:$PATH bash script.sh    # scenario A: .env=v3.2.0 -> edit path; B: =latest -> Already on
```

Both scenarios passed on 50.1 (A: `current=v3.2.0 latest=v3.2.4` → files updated, Z5 line re-added;
B: `Already on v3.2.4`). DB is small (239M) — a `pg_dumpall | gzip` pre-migration safety net costs ~44M
and 30s, worth it before any Immich version bump.

## Current script (v3.0, deployed 2026-10-02)

`/boot/config/plugins/user.scripts/scripts/immich update/script` — parse via `sed -nE` + redirect fallback,
`--max-time` on every curl, `docker compose pull || exit 1` before `up -d`, `docker compose ps` at the end.
Keep the trailing `Z5` re-add block (`sed -i '/\/etc\/localtime/a\ ...'`) — the upstream compose file does
not carry that mount, and `grep -q 'Z5'` guards it against duplicates.
