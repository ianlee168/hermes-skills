#!/usr/bin/env python3
"""拉回线上 worker 模块 → 归一化 → 算 sha256 → 跑部署闸门（漂移检测）。

环境变量
    CF_ACCOUNT_ID   账号 ID（必填）
    CF_API_TOKEN    Workers API token（Bearer）
    CF_API_KEY      Global API Key（与 CF_EMAIL 二选一）
    CF_EMAIL        账号邮箱（配 CF_API_KEY 用）
    SCRIPT_NAME     worker 名，默认 news-xyz-worker

用法
    ./verify_live.py                          # 拉回 + 算哈希 + 跑闸门
    ./verify_live.py --expect <sha256>        # 漂移检测：与基线哈希比对
    ./verify_live.py --out baseline.js        # 另存为基线文件
    ./verify_live.py --show-cost --db <uuid> --sql "SELECT ..."   # 测单条 SQL 的 rows_read

退出码: 0 = 通过/一致, 1 = 闸门不过或哈希不一致
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

BASE = 'https://api.cloudflare.com/client/v4'


def headers():
    tok = os.environ.get('CF_API_TOKEN', '').strip()
    if tok:
        return {'Authorization': 'Bearer ' + tok}
    key = os.environ.get('CF_API_KEY', '').strip()
    email = os.environ.get('CF_EMAIL', '').strip()
    if key and email:
        return {'X-Auth-Email': email, 'X-Auth-Key': key}
    sys.exit('缺少凭据: 需要 CF_API_TOKEN，或 CF_API_KEY + CF_EMAIL')


def call(path, accept=None, data=None, method=None):
    h = headers()
    if accept:
        h['Accept'] = accept
    if data is not None:
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(BASE + path, headers=h, data=data, method=method)
    try:
        raw = urllib.request.urlopen(req, timeout=60).read()
        try:
            return json.loads(raw)
        except Exception:
            return {'_text': raw.decode('utf-8', 'replace')}
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code}: {e.read().decode()[:300]}')


def normalize(raw):
    """剥掉 multipart 外壳 + 结尾空行，并把行尾统一成 LF，得到可比较的模块正文。

    ⚠️ 必须用 splitlines()：Cloudflare 回传的 multipart 行尾是 CRLF，
    若按 '\\n' 切分会留下 '\\r'，字数/哈希就全对不上了。
    """
    lines = raw.splitlines()
    start = 0
    for i, l in enumerate(lines):
        if 'Content-Disposition' in l:
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            start = j
            break
    body = lines[start:]
    while body and body[-1].strip().startswith('--') and body[-1].strip().endswith('--'):
        body.pop()
    while body and body[-1].strip() == '':
        body.pop()
    return ('\n'.join(body) + '\n').encode('utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--expect', help='期望的 sha256（漂移检测）')
    ap.add_argument('--out', help='把归一化后的模块另存到该路径')
    ap.add_argument('--no-gate', action='store_true', help='跳过 predeploy_check')
    ap.add_argument('--show-cost', action='store_true', help='改为测一条 SQL 的 rows_read')
    ap.add_argument('--db', help='D1 database uuid（--show-cost 用）')
    ap.add_argument('--sql', help='要测造的 SQL（--show-cost 用）')
    args = ap.parse_args()

    acct = os.environ.get('CF_ACCOUNT_ID', '').strip()
    if not acct:
        sys.exit('缺少 CF_ACCOUNT_ID')
    name = os.environ.get('SCRIPT_NAME', 'news-xyz-worker')

    if args.show_cost:
        if not (args.db and args.sql):
            sys.exit('--show-cost 需要 --db 和 --sql')
        r = call(f'/accounts/{acct}/d1/database/{args.db}/query',
                 data=json.dumps({'sql': args.sql}).encode())
        rows = r.get('result') or [{}]
        meta = rows[0].get('meta') or {}
        print(f'rows_read = {meta.get("rows_read")}')
        print(f'duration  = {meta.get("duration")} ms')
        n = meta.get('rows_read') or 0
        print('✅ 达标（<200）' if n < 200 else '❌ 超标：必须 <200，回去加索引或走 getStats() 缓存')
        return 0 if n < 200 else 1

    raw = call(f'/accounts/{acct}/workers/scripts/{name}', accept='application/javascript').get('_text', '')
    blob = normalize(raw)
    digest = hashlib.sha256(blob).hexdigest()
    print(f'worker    : {name}')
    print(f'行数/字节 : {len(blob.decode().splitlines())} / {len(blob)}')
    print(f'sha256    : {digest}')

    rc = 0
    if args.expect and digest != args.expect.strip().lower():
        print(f'❌ 漂移！线上与基线不一致。期望 {args.expect.strip().lower()}')
        rc = 1
    elif args.expect:
        print('✅ 与基线一致')

    if args.out:
        pathlib.Path(args.out).write_bytes(blob)
        print(f'已保存    : {args.out}')

    if not args.no_gate:
        gate = pathlib.Path(__file__).with_name('predeploy_check.py')
        tmp = pathlib.Path(args.out) if args.out else pathlib.Path('_live_check.js')
        if not args.out:
            tmp.write_bytes(blob)
        if gate.exists():
            print('\n=== 对线上模块跑闸门 ===')
            r = subprocess.run([sys.executable, str(gate), str(tmp)])
            if r.returncode != 0:
                rc = 1
        else:
            print(f'(跳过闸门：{gate} 不存在)')
    return rc


if __name__ == '__main__':
    sys.exit(main())
