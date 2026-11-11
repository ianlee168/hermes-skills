#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""青龙面板「运行中」残留 体检 / 复位(纯 stdlib, 不依赖 requests, 不需要宿主机 ssh)

面板的「状态」列渲染的是 Crontabs.status 这个**运行态枚举**:

    status = 0 → running(运行中)   status = 1 → idle(空闲)
    status = 2 → disabled(禁用)    status = 3 → queued(排队)

(源码: /ql/static/build/data/cron.js  CrontabStatus[0]="running" …)
所以「一片运行中」= pid 残留 + status 停在 0; 修复必须把空闲行写成 **1**, 已禁用的行写成 **2**。
**千万别写 status=0** —— 0 就是「运行中」, 写 0 会把症状原样复现(实测踩过)。

用法:
    python ql_stale_status.py --panel http://<panel>:6700 --user <u> --password <p>        # 只看
    python ql_stale_status.py --panel http://<panel>:6700 --user <u> --password <p> --fix  # 复位

安全约束(勿改):
  * 不删除任何东西; 只 UPDATE status/pid/queued_token, 且仅限 /proc 里查不到 pid 的行
  * 修改前必定在容器内 shutil.copy2 备份 /ql/data/db/database.sqlite
  * 凭据只从命令行传入, 不要写进本文件(用户的青龙凭据在 gbrain credentials/qinglong)

--fix 的副作用(必须知会用户):
  * 会在面板上新建一个临时任务「面板状态修复(临时)」(占位 schedule, 不会自动跑),
    它自己的行清不掉, 会一直显示“运行中” —— 用完请征得用户同意后删除该任务。
  * 面板任务列表是**一次性拉取不自动刷新**, 修完必须让用户 Ctrl+F5, 否则他会说“还是运行中”。
"""

import argparse
import json
import time
import urllib.error
import urllib.request

TASK_NAME = "面板状态修复(临时)"
PLACEHOLDER_SCHEDULE = "5 5 29 2 *"  # 2月29日, 永不触发

# status 枚举: 0=running 1=idle 2=disabled 3=queued
ST_RUNNING, ST_IDLE, ST_DISABLED, ST_QUEUED = 0, 1, 2, 3

FIX_SRC = '''# -*- coding: utf-8 -*-
import os, shutil, sqlite3, time
DB = "/ql/data/db/database.sqlite"
# 0=running 1=idle 2=disabled 3=queued  —— 修复目标值只能取 1/2
SEL = "SELECT id,name,status,pid,isDisabled FROM Crontabs WHERE status=0 OR pid IS NOT NULL ORDER BY id"
con = sqlite3.connect(DB); cur = con.cursor()
rows = cur.execute(SEL).fetchall()
print("== before ==")
for i, n, st, pid, dis in rows:
    alive = os.path.exists("/proc/%s" % pid) if pid else False
    print("id=%s status=%s pid=%s alive=%s disabled=%s name=%s" % (i, st, pid, alive, dis, n))
bak = "/ql/data/db/full_backup_%s.db" % time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(DB, bak)
print("backup -> %s (%s bytes)" % (bak, os.path.getsize(bak)))
fixed, skipped = [], []
for i, n, st, pid, dis in rows:
    if pid and os.path.exists("/proc/%s" % pid):
        skipped.append(i); print("SKIP 真在跑: id=%s pid=%s %s" % (i, pid, n)); continue
    target = 2 if dis else 1          # 停用->2(disabled)  启用->1(idle)
    cur.execute("UPDATE Crontabs SET status=?, pid=NULL, queued_token=NULL WHERE id=?", (target, i))
    fixed.append((i, target))
con.commit()
print("reset(id,status):", fixed)
print("skipped(live):", skipped)
print("== after ==")
for r in cur.execute(SEL).fetchall():
    print(r)
'''


def api(panel, path, token=None, method="GET", body=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        panel.rstrip("/") + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=headers,
    )
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode("utf-8", "replace")[:300]}
    try:
        return json.loads(raw)
    except ValueError:
        return {"_raw": raw[:300]}


def login(panel, user, password):
    r = api(panel, "/api/user/login", method="POST", body={"username": user, "password": password})
    if not isinstance(r, dict) or "data" not in r:
        raise SystemExit("登录失败: %s" % json.dumps(r, ensure_ascii=False)[:300])
    return r["data"]["token"]


def crons(panel, token):
    r = api(panel, "/api/crons?search=&t=%d" % int(time.time()), token=token)
    return r["data"]["data"]  # 形状是 data.data[], 不是 data 直接为数组


def stale(items):
    """会被渲染成「运行中」的行: pid 非空, 或 status==0(running)。
    status=1/2/3 都不是运行中, 不要把它们当残留。"""
    out = []
    for c in items:
        if c.get("pid") or c.get("status") == ST_RUNNING:
            out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True, help="如 http://192.168.50.1:6700")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--fix", action="store_true", help="复位残留(不传则只体检)")
    a = ap.parse_args()

    token = login(a.panel, a.user, a.password)
    items = crons(a.panel, token)
    bad = stale(items)
    print("任务总数 %d, 渲染成运行中的行 %d" % (len(items), len(bad)))
    for c in bad:
        print("  id=%-6s status=%-3s pid=%-8s disabled=%s  %s"
              % (c["id"], c.get("status"), c.get("pid"), c.get("isDisabled"), c["name"]))
    if not bad:
        print("无残留 ✅ (若面板页面仍转圈: 那是前端一次性拉取没刷新, Ctrl+F5)")
        return
    if not a.fix:
        print("\n只体检未修改。要复位请加 --fix")
        return

    # 1) 部署修复脚本到容器内
    src = {"filename": "_ql_stale_fix.py", "path": "./", "content": FIX_SRC}
    r = api(a.panel, "/api/scripts", token=token, method="POST", body=src)
    if isinstance(r, dict) and r.get("_http_error"):  # 已存在则覆盖
        r = api(a.panel, "/api/scripts", token=token, method="PUT", body=src)
    print("部署修复脚本:", json.dumps(r, ensure_ascii=False)[:120])

    # 2) 建/复用临时任务并触发(占位 schedule, 只能手动 run; id 必须是字符串)
    tid = next((c["id"] for c in items if c["name"] == TASK_NAME), None)
    if tid is None:
        r = api(a.panel, "/api/crons", token=token, method="POST",
                body={"name": TASK_NAME, "command": "python3 /ql/data/scripts/_ql_stale_fix.py",
                      "schedule": PLACEHOLDER_SCHEDULE})
        tid = r.get("data", {}).get("id") if isinstance(r, dict) else None
        print("新建临时任务 id=%s" % tid)
    if not tid:
        raise SystemExit("临时任务创建失败, 请改用面板手动建")
    print("触发:", api(a.panel, "/api/crons/run", token=token, method="PUT", body=[str(tid)]))
    time.sleep(15)

    # 3) 读修复日志(命令首词 = 日志目录名)
    tree = api(a.panel, "/api/logs?t=1", token=token)
    newest = None
    for d in (tree.get("data") or []):
        if d.get("key") == "python3":
            files = sorted(c["title"] for c in d.get("children", []) if c["type"] == "file")
            newest = files[-1] if files else None
    if newest:
        import urllib.parse
        log = api(a.panel, "/api/logs/detail?file=" + urllib.parse.quote("python3/" + newest), token=token)
        print("---- 修复日志 ----")
        print(log.get("data", "")[:1500])

    # 4) 复核 + 后续必做项
    left = stale(crons(a.panel, token))
    print("---- 复核 ----")
    print("仍显示运行中的行:", [(c["id"], c["name"]) for c in left] or "无 ✅")
    print("后续必做: ① 让用户 Ctrl+F5 强刷面板页面(前端不自动刷新);"
          " ② 征得同意后删掉临时任务「%s」(它自己的行清不掉, 会一直转圈);"
          " ③ 若 API 已干净而硬刷后页面仍有成片运行中 → 面板进程内存态残留, 再重启容器。" % TASK_NAME)


if __name__ == "__main__":
    main()
