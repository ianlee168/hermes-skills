#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 qinglong 任务日志, 分类缺模块/错误 (在 qinglong 容器内跑).
用法: docker exec qinglong python3 /ql/data/scripts/scan_jdpro_logs.py
只扫 6dylan6_jdpro* 目录, 改 LOG 前缀可扫全部.
"""
import os, glob, re, datetime

LOG = "/ql/data/log"
results = []
for d in sorted(glob.glob(os.path.join(LOG, "6dylan6_jdpro*"))):
    if not os.path.isdir(d):
        continue
    logs = sorted(glob.glob(os.path.join(d, "*.log")), key=os.path.getmtime)
    if not logs:
        continue
    latest = logs[-1]
    try:
        text = open(latest, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    name = os.path.basename(d)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(latest)).strftime("%H:%M")
    err = ""
    m = re.search(r"Cannot find module '([^']+)'", text)
    if m:
        err = f"缺模块: {m.group(1)}"
    else:
        m = re.search(r"ModuleNotFoundError[^\n]{0,50}", text)
        if m:
            err = f"Python缺模块: {m.group(0)[:60]}"
        else:
            m = re.search(r"Error: [^\n]{0,70}", text)
            if m:
                err = f"错误: {m.group(0)[:70]}"
            else:
                m = re.search(r"❌[^\n]{0,60}", text)
                if m:
                    err = f"失败: {m.group(0)[:60]}"
    ok = bool(re.search(r"领取成功|签到成功|开始【|成功!", text))
    results.append((name, mtime, err, ok))

for name, mtime, err, ok in results:
    flag = "✅" if ok and not err else ("⚠️" if err else "⏳")
    print(f"{flag} {name} | {mtime} | {err}")
print()
print(f"总计 {len(results)} 个任务日志")
