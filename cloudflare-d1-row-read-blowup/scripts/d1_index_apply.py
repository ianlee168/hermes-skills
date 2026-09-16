#!/usr/bin/env python3
"""Land the missing indexes on a D1 database + prove it with EXPLAIN (idempotent).

Why this exists: a "fixed it" cron that only ran --dry-run leaves zero indexes while the
rule doc claims success, so the daily ingest keeps full-scanning (390 x 26k rows = 10.2M/day
= 2x the free tier) and the site 500s every afternoon. DDL is rejected while the account is
over quota, so run this right after the 00:00 UTC reset, with retries.

Usage:
    ./d1_index_apply.py                 # create + verify + site check
    ./d1_index_apply.py --check         # read-only (EXPLAIN costs 0 rows read)
    ./d1_index_apply.py --quiet-if-done # silent when healthy (for a no_agent cron)

Env: CF_ACCOUNT_ID / D1_API_TOKEN (needs D1 Edit) / D1_DATABASE_ID
Exit: 0 = indexes in place, 1 = failed (quota not reset / no rights / CREATE failed)
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

ACCT = os.environ.get('CF_ACCOUNT_ID', '').strip()
TOKEN = (os.environ.get('D1_API_TOKEN') or os.environ.get('CF_D1_TOKEN') or '').strip()
DB = os.environ.get('D1_DATABASE_ID', '').strip()
SITE = os.environ.get('SITE_URL', '').strip()

# EDIT ME: the indexes the hot statements need, and one probe per hot statement.
INDEXES = [
    'CREATE INDEX IF NOT EXISTS idx_posts_cat_created ON posts(category, created_at DESC)',
    'CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)',
    'CREATE INDEX IF NOT EXISTS idx_posts_source_url ON posts(source_url)',
    'CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled)',
]
PROBES = [
    ("ingest dedupe", "SELECT id FROM posts WHERE source_url = 'https://example.com/a'"),
    ("category list", "SELECT id, category FROM posts WHERE category = 'ai' ORDER BY created_at DESC LIMIT 30"),
    ("unfiltered list", "SELECT id FROM posts ORDER BY created_at DESC LIMIT 30"),
]


def d1(sql):
    req = urllib.request.Request(
        f'https://api.cloudflare.com/client/v4/accounts/{ACCT}/d1/database/{DB}/query',
        headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'},
        data=json.dumps({'sql': sql}).encode())
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=90).read())
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        return None, f'HTTP {e.code} {body}'
    except Exception as e:
        return None, str(e)[:200]
    if not r.get('success'):
        return None, json.dumps(r.get('errors'), ensure_ascii=False)[:220]
    first = (r.get('result') or [{}])[0]
    if not first.get('success'):
        return None, json.dumps(first.get('errors'), ensure_ascii=False)[:220]
    return first, None


# Build cost gate: free tier is 100,000 rows_written/day (a SEPARATE limit from rows read).
# Creating an index writes one row per table row per index, so a rebuild on a big table can
# exhaust the day's write budget by itself (26k rows x 3 indexes = 78k = 79% of the cap).
WRITE_GUARD = int(os.environ.get('D1_WRITE_GUARD', '90000'))
TABLE_INDEXES = [i for i in INDEXES if ' ON posts(' in i]


def write_cost_guard():
    """Estimate the write cost of the DDL and refuse above the safety line.

    True = go ahead, False = refuse (a rebuild would blow rows_written and 500 the site).
    """
    r, err = d1('SELECT COUNT(*) AS n FROM posts')  # EDIT ME: the table being indexed
    if r is None:
        print(f'  write-cost estimate failed ({err[:100]}) -- proceeding unverified')
        return True
    rows = ((r.get('results') or [{}])[0] or {}).get('n') or 0
    est = rows * len(TABLE_INDEXES)
    print(f'  write cost: {rows:,} rows x {len(TABLE_INDEXES)} indexes = {est:,} rows_written'
          f' ({est / 100000 * 100:.1f}% of the 100,000/day cap)')
    if est > WRITE_GUARD:
        print(f'  REFUSING: estimate {est:,} exceeds safety line {WRITE_GUARD:,} (cap 100,000)')
        print('  A rebuild here would exhaust rows_written and take the site down.')
        print('  Do one index per day instead.')
        return False
    return True


def plan_uses_index():
    """EXPLAIN QUERY PLAN costs 0 rows read, so it works even under a blown quota."""
    ok_all, lines = True, []
    for label, sql in PROBES:
        r, err = d1('EXPLAIN QUERY PLAN ' + sql)
        if r is None:
            ok_all = False
            lines.append((label, f'no plan: {err}'))
            continue
        details = [str(row.get('detail') or '') for row in (r.get('results') or [])]
        uses = bool(details) and all('USING INDEX' in d for d in details)
        ok_all = ok_all and uses
        lines.append((label, ('OK  ' if uses else 'BAD ') + ' | '.join(details)))
    return ok_all, lines


def site_code(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'index-check'}), timeout=25) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 'ERR'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--dry-run', action='store_true', help='estimate the rebuild write cost only')
    ap.add_argument('--quiet-if-done', action='store_true')
    ap.add_argument('--max-attempts', type=int, default=4)
    ap.add_argument('--retry-wait', type=int, default=150)
    args = ap.parse_args()
    if not (ACCT and TOKEN and DB):
        print('missing CF_ACCOUNT_ID / D1_API_TOKEN / D1_DATABASE_ID')
        return 1

    done, lines = plan_uses_index()

    if args.dry_run:
        print(f'current state: {"indexes in place" if done else "indexes MISSING (a rebuild would really write)"}')
        for label, txt in lines:
            print(f'  {label}: {txt}')
        ok = write_cost_guard()
        print('  [dry-run] no DDL executed')
        return 0 if ok else 1

    if done:
        if args.quiet_if_done:
            return 0
        print('indexes already in place')
        for label, txt in lines:
            print(f'  {label}: {txt}')
        return 0
    if args.check:
        print('hot statements still SCAN (indexes missing):')
        for label, txt in lines:
            print(f'  {label}: {txt}')
        return 1

    if not write_cost_guard():
        return 1

    print('landing indexes (DDL is rejected while over quota, hence retries)')
    for label, txt in lines:
        print(f'  before {label}: {txt}')
    failed = None
    for attempt in range(1, args.max_attempts + 1):
        created, failed = [], []
        for sql in INDEXES:
            r, err = d1(sql)
            (created if r is not None else failed).append((sql, (r.get('meta') if r else err)))
        if not failed:
            failed = None
            break
        if attempt < args.max_attempts:
            print(f'  attempt {attempt} failed: {str(failed[0][1])[:120]} -- retrying in {args.retry_wait}s')
            time.sleep(args.retry_wait)
    if failed:
        print('FAILED to create indexes -- the hot statements keep full-scanning:')
        for sql, err in failed:
            print(f'  {sql[:70]} -> {str(err)[:150]}')
        return 1

    done, lines = plan_uses_index()
    for label, txt in lines:
        print(f'  after {label}: {txt}')
    if SITE:
        print(f'  site: / -> HTTP {site_code(SITE)}  /api/posts -> HTTP {site_code(SITE.rstrip("/") + "/api/posts")}')
    if not done:
        print('indexes created but plans still SCAN -- look closer')
        return 1
    print('indexes in place and verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
