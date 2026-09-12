#!/usr/bin/env python3
"""news-xyz 部署前置闸门 —— 静态检查即将上传的 worker 文件。

把 RULES.md 从"纸面约定"变成"机械闸门"：命中任一条就拒绝部署。

用法:
    python predeploy_check.py src/index.js
    python predeploy_check.py src/index.js --binding news_xyz_db --max-ttl-floor 3600
    python predeploy_check.py src/index.js --no-node-check

退出码: 0 = 通过, 1 = 拒绝部署
"""
import argparse
import re
import shutil
import subprocess
import sys

# 每次请求路径上都算全表扫描的写法
COSTLY = re.compile(r'COUNT\(\*\)|SUM\(|AVG\(|GROUP BY', re.I)
# 这些是允许的"缓存入口"标记
CACHE_ENTRY = 'getStats('
LOOKBACK = 6          # 往上看几行找 getStats(


def fail(msgs, line, text):
    msgs.append((line, text))


def is_comment(line):
    s = line.strip()
    return s.startswith('//') or s.startswith('*') or s.startswith('/*')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--binding', default='news_xyz_db',
                    help='必须出现的 D1 绑定名（默认 news_xyz_db）')
    ap.add_argument('--no-node-check', action='store_true')
    args = ap.parse_args()

    try:
        src = open(args.path, encoding='utf-8').read()
    except OSError as e:
        print(f'❌ 读不到文件: {e}')
        return 1

    lines = src.splitlines()
    errors = []
    notes = []

    # 1) 禁止任何自动轮询
    for i, l in enumerate(lines):
        if 'setInterval(' in l or 'setTimeout(' in l and 'loadAdmin' in l:
            fail(errors, i + 1, l.strip()[:110])

    # 2) 聚合查询必须包在 getStats() 里（注释行不算，否则闸门会被自己的说明文字绊倒）
    for i, l in enumerate(lines):
        if is_comment(l):
            continue
        if COSTLY.search(l):
            ctx = '\n'.join(lines[max(0, i - LOOKBACK):i + 1])
            if CACHE_ENTRY not in ctx:
                fail(errors, i + 1, l.strip()[:110])

    # 3) getStats 必须真的存在
    if 'function getStats(' not in src and 'getStats = ' not in src:
        errors.append((0, '找不到 getStats() 定义 —— 缓存层被删了？'))

    # 4) 统计缓存 TTL 不许小于 1 小时（缓存是全局的，TTL 越短全扫次数越多）
    ttl_floors = {
        'category_counts': 3600,
        'views_total': 3600,
    }
    for key, floor in ttl_floors.items():
        for m in re.finditer(r'getStats\([^)]*?["\']' + key + r'["\'](.{0,200}?)\)', src, re.S):
            tail = m.group(1)
            nums = [int(n) for n in re.findall(r'\b(\d{2,6})\b', tail)]
            if nums and max(nums) < floor:
                errors.append((0, f'{key} 的 TTL {max(nums)}s < {floor}s —— 全局缓存，TTL 太短反而更糟'))

    # 5) D1 绑定名必须在场
    if args.binding and args.binding not in src:
        errors.append((0, f'找不到 D1 绑定名 {args.binding} —— 上传 metadata 写错就会静默丢绑定'))

    # 6) 语法必须过
    if not args.no_node_check:
        node = shutil.which('node')
        if node:
            import os
            import tempfile
            with tempfile.NamedTemporaryFile('w', suffix='.mjs', delete=False, encoding='utf-8') as f:
                f.write(src)
                tmp = f.name
            try:
                r = subprocess.run([node, '--check', tmp], capture_output=True, text=True)
                if r.returncode != 0:
                    errors.append((0, 'node --check 失败: ' + (r.stderr or '').strip().splitlines()[-1][:120]))
            finally:
                os.unlink(tmp)
        else:
            notes.append('本机没有 node，跳过语法检查')

    # 7) 参考信息（不算失败）
    notes.append(f'setInterval 出现 {src.count("setInterval")} 次')
    notes.append(f'getStats 出现 {src.count("getStats")} 次')
    notes.append(f'行数 {len(lines)}')

    print(f'=== predeploy_check: {args.path} ===')
    for n in notes:
        print('  · ' + n)
    if errors:
        print(f'\n❌ 拒绝部署 —— {len(errors)} 处不合规:')
        for ln, txt in errors:
            where = f'L{ln}' if ln else '--'
            print(f'  {where:>6}  {txt}')
        print('\n修复方向: 加索引 / 走 getStats(env, key, sql, >=3600) / 删掉轮询。')
        return 1
    print('\n✅ 通过，可以部署。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
