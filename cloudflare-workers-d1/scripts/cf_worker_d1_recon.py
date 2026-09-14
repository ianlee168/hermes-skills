#!/usr/bin/env python3
"""Cloudflare Workers + D1 recon.

Pulls the Cloudflare tokens out of gbrain, so no secret is ever typed into a
command line or printed. Default mode is METADATA ONLY: it lists Workers, their
D1 bindings and cron triggers, and the D1 databases. It does not read table
rows, so it cannot add to a blown row-read quota.

Usage:
  python3 cf_worker_d1_recon.py                    # workers + bindings + crons, D1 list
  python3 cf_worker_d1_recon.py --worker NAME       # + SQL literals, crons, bindings for that worker
  python3 cf_worker_d1_recon.py --sql               # SQL literals for every worker
  python3 cf_worker_d1_recon.py --d1 NAME_OR_UUID   # D1 detail + SELECT 1 scope probe
  python3 cf_worker_d1_recon.py --probe             # OPT-IN: SELECT 1 against every DB

Never prints tokens. Never mutates anything (GET only, plus the opt-in probe).
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request

BASE = 'https://api.cloudflare.com/client/v4'


def load_creds():
    """Return (list_of_cfut_tokens, global_api_key_or_None)."""
    try:
        out = subprocess.run(['gbrain', 'get', 'credentials/api-keys'],
                             capture_output=True, text=True, timeout=180).stdout
    except Exception as exc:  # pragma: no cover
        sys.exit('could not read gbrain credentials: %s' % exc)
    tokens = re.findall(r'cfut_[A-Za-z0-9]+', out)
    gk = re.search(r'Global API Key\*\*:\s*`([A-Za-z0-9]+)`', out)
    if not tokens and not gk:
        sys.exit('no Cloudflare credentials found under credentials/api-keys')
    return tokens, (gk.group(1) if gk else None)


def req(path, token, accept=None, data=None):
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
    if accept:
        headers['Accept'] = accept
    r = urllib.request.Request(BASE + path, headers=headers, data=data)
    try:
        raw = urllib.request.urlopen(r, timeout=35).read()
    except Exception as exc:
        body = ''
        try:
            body = exc.read().decode()[:300]
        except Exception:
            pass
        return {'_error': str(exc), '_body': body}
    try:
        return json.loads(raw)
    except Exception:
        return {'_text': raw.decode('utf-8', 'replace')}


def pick_account(token):
    r = req('/accounts', token)
    if not isinstance(r, dict) or not r.get('success'):
        sys.exit('cannot list accounts with the Workers token: %s' % json.dumps(r)[:200])
    accts = r.get('result') or []
    for a in accts:
        print('ACCOUNT %s  %s' % (a.get('id'), a.get('name')))
    return accts[0]['id'] if accts else None


def d1_token(tokens, aid):
    """First stored token that can actually list D1 databases."""
    for t in tokens:
        r = req('/accounts/%s/d1/database' % aid, t)
        if isinstance(r, dict) and r.get('success'):
            return t, (r.get('result') or [])
    return None, []


SQL_RE = re.compile(r'[`\'"]([^`\'"]*?\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^`\'"]*?)[`\'"]',
                    re.I | re.S)


def sql_literals(src):
    seen, out = set(), []
    for hit in SQL_RE.findall(src):
        q = ' '.join(hit.split())
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def show_worker(tok, aid, name, with_sql):
    print('\n== %s' % name)
    bound = []
    st = req('/accounts/%s/workers/scripts/%s/settings' % (aid, name), tok)
    if isinstance(st, dict) and st.get('success'):
        for b in ((st.get('result') or {}).get('bindings') or []):
            target = b.get('database_name') or b.get('id') or b.get('class_name') or ''
            print('   BINDING %-14s %-16s -> %s' % (b.get('type'), b.get('name'), target))
            if b.get('type') in ('d1', 'd1_databases'):
                bound.append(b.get('database_name') or b.get('id'))
    else:
        print('   settings err: %s' % str(st)[:160])

    sc = req('/accounts/%s/workers/scripts/%s/schedules' % (aid, name), tok)
    res = sc.get('result') if isinstance(sc, dict) else None
    # result is {"schedules": [...]}; iterating the dict itself yields the KEY name.
    scheds = (res or {}).get('schedules') if isinstance(res, dict) else None
    for c in (scheds or []):
        print('   CRON %s' % (c.get('cron') if isinstance(c, dict) else c))

    src = req('/accounts/%s/workers/scripts/%s' % (aid, name), tok,
              accept='application/javascript').get('_text', '')
    if src:
        print('   src %d bytes | .prepare( x%d | count(*) x%d | SELECT x%d' % (
            len(src), src.count('.prepare('), src.lower().count('count(*)'),
            src.lower().count('select ')))
        if with_sql:
            for q in sql_literals(src):
                print('     * %s' % q[:200])
    return bound


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--account', help='account id (default: first from /accounts)')
    ap.add_argument('--worker', help='dump one worker in detail')
    ap.add_argument('--sql', action='store_true', help='dump SQL literals for every worker')
    ap.add_argument('--d1', help='D1 database name or uuid to describe + probe')
    ap.add_argument('--probe', action='store_true', help='OPT-IN: SELECT 1 against every DB')
    a = ap.parse_args()

    tokens, _gkey = load_creds()
    if not tokens:
        sys.exit('no cfut_ token found (only a Global API Key); add an API token')
    wtok = tokens[0]
    aid = a.account or pick_account(wtok)
    if not aid:
        sys.exit('no account')

    dtok, dbs = d1_token(tokens, aid)
    print('\nD1 token usable: %s | databases: %d' % (bool(dtok), len(dbs)))
    for db in dbs:
        print('   DB %-16s %s  created %s' % (db.get('name'), db.get('uuid'), db.get('created_at')))
        det = req('/accounts/%s/d1/database/%s' % (aid, db['uuid']), dtok)
        r = (det.get('result') or {}) if isinstance(det, dict) else {}
        print('      tables=%s file_size=%s region=%s' % (
            r.get('num_tables'), r.get('file_size'), r.get('running_in_region')))

    sub = req('/accounts/%s/workers/subdomain' % aid, wtok)
    sres = (sub.get('result') or {}) if isinstance(sub, dict) else {}
    sd = sres.get('subdomain')
    print('\nworkers.dev subdomain: %s -> https://<worker>.%s.workers.dev/' % (sd, sd))

    scripts = req('/accounts/%s/workers/scripts' % aid, wtok)
    names = [x.get('id') for x in ((scripts.get('result') or []) if isinstance(scripts, dict) else [])]
    print('\nWORKERS: %s' % ', '.join(names))

    for n in ([a.worker] if a.worker else names):
        show_worker(wtok, aid, n, with_sql=a.sql or bool(a.worker))

    targets = []
    if a.d1:
        targets = [d for d in dbs if a.d1 in (d.get('name'), d.get('uuid'))]
        if not targets:
            print('\nno D1 database matches %r' % a.d1)
    elif a.probe:
        targets = dbs
    for d in targets:
        r = req('/accounts/%s/d1/database/%s/query' % (aid, d['uuid']), dtok,
                data=json.dumps({'sql': 'SELECT 1 AS ok'}).encode())
        print('\nPROBE %s -> %s' % (d['name'], json.dumps(r, ensure_ascii=False)[:400]))
    if a.probe:
        print('\nNOTE: a 7500 error means reads are gated. Success with rows_read=0 does NOT '
              'prove the gate is open — query a real table to be sure.')


if __name__ == '__main__':
    main()
