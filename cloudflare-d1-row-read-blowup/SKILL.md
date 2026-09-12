---
name: cloudflare-d1-row-read-blowup
description: "Use when Cloudflare D1 hits the daily row-read limit."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Cloudflare, D1, Workers, Quota, Performance]
    related_skills: [blocked-page-recovery]
---

# Cloudflare D1 row-read blowup

Symptom: an email from Cloudflare ("You have exceeded the daily D1 free tier
limit of 5000000 rows read"), the Worker returns
`D1_ERROR: Your account has exceeded D1's free tier daily row read limit`,
and DB-backed routes flip to `error code: 1101` (uncaught JS exception —
because the endpoint's `.prepare().all()` has no try/catch).

Free tier = **5,000,000 rows read/day**, reset at **00:00 UTC**. Data is never
lost; only reads fail. The limit is enforced on rows actually touched, so a
`SELECT 1` or a `sqlite_master` query still succeeds while a real scan fails.

## Diagnose (cheap, no LLM guessing)

1. Get the D1 database size and row count. The `/query` endpoint's
   `meta.rows_read` is the ground truth for cost:

   ```bash
   curl -s -X POST \
     "https://api.cloudflare.com/client/v4/accounts/$AID/d1/database/$DB/query" \
     -H "Authorization: Bearer $D1_TOKEN" -H 'Content-Type: application/json' \
     -d '{"sql":"SELECT COUNT(*) AS n FROM posts"}'
   ```

   `rows_read` in the response = the table size = what one full scan costs.
   Divide 5,000,000 by it to get "how many such queries the free tier allows".

2. Pull the Worker source and count the per-request scans:
   `GET /accounts/{aid}/workers/scripts/{name}` with
   `Accept: application/javascript`. The body comes back wrapped in a
   **multipart envelope** — strip the leading
   `--<boundary>` / `Content-Disposition` lines **and the trailing
   `--<boundary>--` line** before the code is valid JS.

3. Look for, in this order of nastiness:
   - `setInterval(<fetch to an endpoint>, 15000)` in the inlined HTML/JS — a
     dashboard left open polls forever. One open tab at 15s x a full scan
     exhausts 5M in well under an hour.
   - Per-request aggregates: `SELECT COUNT(*) ... GROUP BY`,
     `SELECT SUM(col) FROM t`, `SELECT * FROM t ORDER BY <unindexed> DESC LIMIT n`.
   - A loop over N categories each running its own `ORDER BY ... LIMIT` query.

## Fix

Order matters: **DDL is blocked while over quota** (CREATE TABLE / CREATE INDEX
read the table), so schema work has to wait for the 00:00 UTC reset.

1. **Index the query shapes** (idempotent, additive, no code deploy):

   ```sql
   CREATE INDEX IF NOT EXISTS idx_posts_cat_created ON posts(category, created_at DESC);
   CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC);
   CREATE INDEX IF NOT EXISTS idx_posts_source_url ON posts(source_url);
   CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled);
   ```

   A composite index turns `WHERE category=? ORDER BY created_at DESC LIMIT n`
   from a full scan into ~n rows read.

2. **Cache the aggregate queries in a `stats` table** — indexes do NOT help
   `GROUP BY`/`SUM`, which still touch every row per request:

   ```sql
   CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL);
   ```

   ```js
   async function getStats(env, key, sql, maxAgeSec) {
     const now = Math.floor(Date.now() / 1e3);
     try {
       const row = await env.DB.prepare("SELECT value, updated_at FROM stats WHERE key = ?").bind(key).first();
       if (row && maxAgeSec > 0 && now - Number(row.updated_at) < maxAgeSec) return JSON.parse(row.value);
     } catch (e) { console.log("stats read failed:", e.message); }
     const { results } = await env.DB.prepare(sql).all();
     try {
       await env.DB.prepare("INSERT INTO stats (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at")
         .bind(key, JSON.stringify(results || []), now).run();
     } catch (e) { console.log("stats write failed:", e.message); }
     return results || [];
   }
   ```

   **TTL must be >= 1 hour.** A DB-backed cache is *global*, not per-colo, so
   scan count/day = 86400/TTL. TTL 60s = 1440 scans/day — worse than the bug
   you are fixing. 3600s = 24 scans/day.

3. **Delete the poller — do not just slow it down.** A dashboard that polls an
   aggregate endpoint is a landmine: at 15s x a 26k-row scan, ~48 minutes with
   the tab open exhausts a whole day's quota. Replace
   `setInterval(fn, 15000)` with load-on-open plus the existing manual refresh
   button, and delete the interval entirely — merely slowing it to 60s leaves
   the trap armed for the next time someone shortens a cache TTL.
   (A panel whose ✕ removes the DOM node usually stops the burn even while the
   interval spins: the handler writes into the removed node and throws before
   reaching `fetch`.)

4. Refresh the cached keys at the end of the Worker's `scheduled()` handler by
   calling the same helper with `maxAgeSec = 0` (forces a refresh).

## Deploying a patched Worker through the API

Use `curl -F` with the Global API Key (`X-Auth-Email` + `X-Auth-Key`).

**The single most important gotcha:** the module part MUST carry an explicit
`filename=` equal to `main_module`. Without it Cloudflare rejects the upload
with `10021 Uncaught Error: No such module: index.js`, *even for a 5-line
hello-world module* — so do not waste time debugging your patch:

```bash
curl -sS -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$AID/workers/scripts/$NAME" \
  -H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_GKEY" \
  -F "metadata=@meta.json;type=application/json" \
  -F "index.js=@worker.js;filename=index.js;type=application/javascript+module"
```

`meta.json` must repeat the existing `compatibility_date` and **every existing
binding** (fetch them from `.../workers/scripts/{name}/settings` first) — a
multipart upload replaces the whole configuration and silently drops anything
left out.

Verify after upload: re-read `/settings` (bindings + compatibility_date),
re-download the script and grep for your new symbols, and check
`/versions?per_page=1` still reports `handlers: [fetch, scheduled]`.

## Ship a mechanical gate, not a rule

A rule in a README does not survive a well-meaning deploy — including one
from another agent. Make the deploy script run
`scripts/predeploy_check.py` and **refuse to upload** when it fails:

- any `setInterval(` (or polling-style `setTimeout`)
- `COUNT(*)` / `SUM(` / `AVG(` / `GROUP BY` with no `getStats(` within the
  previous 6 lines (comment lines exempt, or the gate trips on its own docs)
- a missing `getStats` definition
- a `getStats` TTL below 3600 for the aggregate keys
- a missing D1 binding name in the module
- `node --check` failure

After deploying, re-download the module and run the same check on it: that is
the drift detector, and it is how you prove the live worker matches the repo
baseline. Pin the baseline with a sha256 taken from a *deterministic*
extraction (strip the multipart envelope, strip trailing blank lines, join
with `\n`, append one `\n`) — the hash of the file you uploaded will differ
from the hash of the module you download back, because Cloudflare normalises
trailing blank lines.

## Pitfalls

- A `cfut_`-prefixed Workers API token can read scripts but returns
  `403 Authentication error` on PUT. Script upload needs Workers Scripts:Edit
  — use the Global API Key.
- Keep the pre-patch module on disk before uploading; rollback is the same
  PUT with the backup file.
- Validate the patched bundle with `node --check file.mjs` (copy to `.mjs`
  first) before deploying.
- Strip the multipart trailer before syntax-checking a downloaded bundle, or
  `node --check` fails on the trailing `--<boundary>--` line.
- Don't create the `stats` table by hand during an outage — the CREATE is
  blocked by the same read limit; put it in the post-reset job.

## Scripts

- `scripts/cf_worker_put.sh` — upload a pre-bundled ES-module Worker, with the
  required `filename=` form field baked in.
