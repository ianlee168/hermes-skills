---
name: cloudflare-workers-d1
description: "Use when Cloudflare Workers/D1 breaks or blows quota."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Cloudflare, Workers, D1, Quota, Serverless, Triage]
    related_skills: [blocked-page-recovery]
---

# Cloudflare Workers + D1

Recon and triage for this user's Cloudflare account: find which Worker is
degraded, which D1 database it hammers, and whether the fix is free or costs
money.

Trigger cases: a Cloudflare quota/limit notification arrives, a Worker-powered
site returns 5xx, or the user asks what is running on their Cloudflare account.

**Always run the recon script — never answer from the notification text
alone.** The email says what tripped; only the API says where the usage went.

## Procedure

1. **Pull credentials out of gbrain, never out of the chat.**
   `gbrain get credentials/api-keys` has a `### Cloudflare` section: Workers
token, Global API Key, D1 Access Token. The account is
`<USER_EMAIL>'s Account`.
2. **Keep tokens out of command text and out of the reply.** Extract inside the
   shell (`TOK=$(gbrain get credentials/api-keys | grep -o 'cfut_[A-Za-z0-9]*' | head -1)`)
   and pass `$TOK`. Never print a token, never paste one back to the user.
3. **Run the recon script** (metadata only — costs nothing against quota):

   ```bash
   python3 scripts/cf_worker_d1_recon.py
   python3 scripts/cf_worker_d1_recon.py --worker <name> --sql   # SQL literals + crons + bindings
   python3 scripts/cf_worker_d1_recon.py --d1 <name>            # D1 detail + token scope check
   ```

4. **Rank the candidates.** Fat D1 `file_size` x per-request query plan = the
   culprit. Attach the culprit to a Worker via the `D1Database`/`d1` binding in
   `/workers/scripts/{name}/settings`, then read that Worker's SQL literals.
5. **Confirm real-world impact** with one curl of the public route:
   `curl -s -o /dev/null -w '%{http_code}' https://<worker>.<subdomain>.workers.dev/`.
   An SSR Worker surfaces the D1 error as a 500 with the D1 message in the body.
6. **Report the live-verified state, not the notification.** Quote the API/HTTP
   evidence (error code, `http_code`, DB size, the actual query), then give the
   fix ladder. 先查证再答.

`references/d1-quota-triage.md` carries the error codes, free-tier numbers, the
`rows_read` measurement recipe, and the fix ladder.

## Fix ladder — cheapest first, and the user pays nothing by default

| Order | Fix | Cost |
|---|---|---|
| 1 | Do nothing if the reset is hours away | free — data is never lost, only reads error |
| 2 | Index the ORDER BY / GROUP BY columns; cache the hot page in KV; rate-limit the public route | free, fixes the cause |
| 3 | Upgrade to Workers Paid (min $5/mo, 25B rows read/mo) | **monetary** |

This user is cost-sensitive. **Never upgrade a plan, enable billing, or change
any paid setting on your own** — monetary actions need explicit consent each
time. Lead with fix 2 and show the numbers that make $5 unnecessary.

## API notes that cost time if you miss them

- `/workers/scripts/{name}/content` returns **405**. Get source with
  `GET /accounts/{a}/workers/scripts/{name}` and header
  `Accept: application/javascript`.
- `/workers/scripts/{name}/schedules` returns `result` as a dict
  (`{"schedules":[...]}`). Iterating `result` directly yields the string
  `"schedules"` and looks like a cron named "schedules" — read
  `result["schedules"]`.
- `/workers/routes` returns 400 code 7003 with a Workers-scoped token. That is a
  missing scope, not "no routes" — don't report the Worker as unrouted.
- `GET /accounts/{a}/workers/scripts` uses `id` for the script name.
- Per-SQL usage attribution exists: `d1QueriesAdaptiveGroups { dimensions { query error } }`
  has a `query` dimension (`d1AnalyticsAdaptiveGroups` does not). Aggregate `sum.rowsRead` by
  `query` and `datetimeHour` before blaming a route — a daily ingest cron doing
  `SELECT ... WHERE url = ?` unindexed can be 90%+ of the day while the homepage is ~5%.
- workers.dev is enabled on this account (subdomain `ianlee168`), so every
  Worker is publicly reachable at `https://<worker>.ianlee168.workers.dev/` and
  crawlable by bots. Factor that in before blaming the user's own traffic.
- Cloudflare Tunnel credentials for this user live in `~/.cloudflared/`
  (`AccountTag` there cross-checks the account id the API returns).

## Pitfalls

- **The token API cannot tell you whether a token may WRITE — the statement can.**
  `/user/tokens/verify` answers `"status": "active"` without exposing any scopes, and reading the
  token detail can come back `403` / `9109 Unauthorized to access requested resource`, so neither
  proves D1 Edit rights. The only honest proof is running the statement and reading its result:
  keep "no rights" (auth/authorization code, e.g. `7403`) distinct from "quota locked" (`7500`) when
  you report, and if you cannot test before the reset window, say the DDL right is *unverified*
  rather than assuming it — a read-only token fails the scheduled remediation the next morning.
- **Two `cfut_` tokens exist and they are not interchangeable.** The Workers
  token fails `/d1/database` with `{"code":10000,"message":"Authentication
  error"}`. gbrain's annotation claiming only a `ca_` token has D1 rights is
  stale — the second stored token lists and queries D1 fine. Try every stored
  token before telling the user you lack access.
- **A successful probe is not proof the limit is clear.** Enforcement fires on
  rows actually read, so `SELECT 1` (0 rows) keeps working while every real
  query returns 7500. Probe with a query that reads a real table.
- **`LIMIT n` does not cap rows read.** SQLite scans every row to ORDER BY an
  unindexed column or to compute COUNT(*)/SUM()/GROUP BY before applying the
  limit, so a "cheap" 100-row page read can bill tens of thousands of row reads.
- **A once-daily cron cannot blow a daily quota.** If the crons are daily and
  the binding is to a small DB, the usage is coming from the per-request
  queries on the public route.
- **Verify a fix with per-statement cost, not the daily total.** Re-query each hot statement and
  compare `meta.rows_read` against its pre-fix value (an indexed dedupe lookup goes from table-size
  to ~0; a `LIMIT n` list goes to ~n). The daily analytics total lags a day and mixes one-time work.
- **The day the indexes land spikes — that is not a failure.** `CREATE INDEX` itself reads the table
  (~2x table size per index; four indexes over a 26k-row table ≈ 528k rows), so the usage alert can
  fire on the very day the fix worked. Judge the first full day after, or the per-statement numbers.
- **Indexes never help `COUNT(*)` / `GROUP BY` / `SUM`.** Expect a small full-scan residual (a couple
  of scans a day once the cache is warm) and convert those to cached or incremental counters before
  the table outgrows the cache.
- Don't run measurement queries (COUNT(*), SUM, GROUP BY) while the account is
  already over the limit — they cannot succeed and add nothing. `--probe` in the
  script is opt-in for that reason.
