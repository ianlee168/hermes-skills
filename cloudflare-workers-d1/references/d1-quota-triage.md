# D1 quota triage

## The notification, decoded

A D1 limit email means one thing: the account burned a **daily** row-read
allowance. It is not corruption and not data loss.

| Email says | Actually means |
|---|---|
| "Operation: Rows read" | the metered unit is **rows scanned**, not requests and not rows returned |
| "You have exceeded the daily D1 free tier limit" | reads now fail; writes and stored data are untouched |
| "Reset time: ... 00:00:00 UTC" | the free tier resets at **midnight UTC** = 08:00 Beijing |
| "restore service by upgrading to the Workers Paid plan" | upsell, min $5/mo, 25B rows read + 50M rows written per month |

Free-tier shape: **5,000,000 rows read/day** on the Workers Free plan.

## Enforcing error

```
HTTP 400  {"success":false,"errors":[{"code":7500,
  "message":"Your account has exceeded D1's free tier daily row read limit.
   Upgrade to a paid plan or wait until tomorrow (midnight UTC) to continue."}]}
```

Same message reaches the browser when an SSR Worker hits the DB:
`SSR_ERROR: D1_ERROR: ... limit ...`, served as HTTP 500 by the Worker, while a
non-DB Worker's `/` still returns 200. That curl is the cheapest proof of
user-visible impact.

**The gate is on rows read, not on requests.** `SELECT 1` reads 0 rows and keeps
succeeding while every real query 7500s. Never report "reads work" off a
`SELECT 1` probe — measured `rows_read` is the truth.

## Measuring what a page view costs

The D1 query API returns the meter inline, so one probe query shows the rows read
per page view:

```bash
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$AID/d1/database/$UUID/query" \
  -H "Authorization: Bearer $DTOK" -H 'Content-Type: application/json' \
  --data '{"sql":"SELECT * FROM posts ORDER BY created_at DESC LIMIT 100"}' \
| python3 -c 'import json,sys; m=json.load(sys.stdin)["result"][0]["meta"]; print("rows_read", m["rows_read"], "ms", m["duration"])'
```

Run the Worker's own hot queries verbatim (lift them from the script source with
`--sql`), compare each `rows_read`, then multiply by plausible daily page views.
Table size is readable for free: `/accounts/{a}/d1/database/{uuid}` gives
`file_size` and `num_tables`, and `SELECT COUNT(*) FROM t` reports roughly the
table's row count in `rows_read`.

Do **all** of this after the quota resets, or while the DB is healthy. It is
impossible while the gate is shut, and retrying it then just wastes calls.

## Rank the suspects

1. Fat DB x per-request scan = culprit. A 34 MB database with 2 tables dwarfs a
   36 KB one; both can be bound to different Workers, and only one matters.
2. `SELECT * FROM t ORDER BY <unindexed> ... LIMIT n` and `COUNT(*)` / `SUM()` /
   `GROUP BY` are full scans. `LIMIT` is applied **after** the sort or aggregate,
   so it does not cap rows read.
3. Daily cron triggers cannot produce a daily quota blowout. If every cron is
   `0 2 * * *` and binds a small DB, the usage is per-request, from the public
   route.
4. Check whether the deployment is public: `workers.dev` subdomains are
   internet-reachable and crawlable, so bot traffic can be the missing order of
   magnitude.

## Fix ladder

**1 — Wait.** Only reads are gated; nothing is lost. If the reset is hours away,
say so and stop. Free.

**2 — Cut the scans.** Free, and it is the real fix:

```sql
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_category_created ON posts (category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_source_url ON posts (source_url);
```

Also: cache the hot page in KV or the Cache API instead of re-querying per
request; move the per-view `UPDATE posts SET view_count = view_count + 1` to a
batched or asynchronous write; rate-limit or front the public route with a
Firewall rule. Two orders of magnitude less rows read keeps it inside the free
tier.

**3 — Upgrade.** Workers Paid, min **$5/mo**, 25B rows read/month — far more
headroom than a personal site needs. **Monetary: requires explicit user consent
every time.** Never upgrade, enable billing, or touch a paid setting on your own
initiative. This user is cost-sensitive: present fix 2 and the numbers that make
fix 3 unnecessary before even naming the price.

## Reporting shape that works here

Lead with live-verified evidence, not the notification: the error code, the
`http_code` of the public route, the DB `file_size`, the exact query that scans.
Then say plainly which parts are measured and which are inferred (e.g. "indexes
missing" is inference from the SQL until `sqlite_master` can actually be read).
Then the ladder. 先查证再答.
