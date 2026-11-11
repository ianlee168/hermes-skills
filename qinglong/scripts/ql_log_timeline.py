#!/usr/bin/env python3
"""青龙任务「逐日失败时间线」: 一次答清「从哪天开始坏、报的什么错」。

场景: 用户说某个签到任务「没了 / 不签到了」。任务往往还在、还启用,只是连着
几天失败没结果。别再一天一天点日志,直接跑这个。

用法:
  python3 ql_log_timeline.py --match avatr
  python3 ql_log_timeline.py --match jesting --last 10
  python3 ql_log_timeline.py --dirs avatr_sign jesting_jesting --last 14

凭证: 优先 QL_TOKEN 环境变量; 否则 QL_USER/QL_PASS 换新 token(默认从 gbrain
credentials/qinglong 的记录里抄, 或 --user/--pass 传)。全程不打印 token/凭证。

纯 stdlib, 任意平台可跑(Windows 下用 python, 不要用 /c/... 路径喂给本脚本)。
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ERR_RE = re.compile(r"(❌|Error|ERROR|错误|异常|Traceback|ModuleNotFoundError|Forbidden|502|502:|401)")
OUT_OK = "完成 ✅"
OUT_FAIL = "失败 ❌"


def req(url, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url + path, data=data, headers=headers,
                               method="POST" if data else "GET")
    with urllib.request.urlopen(r, timeout=40) as resp:
        return json.load(resp)


def get_token(url, user, password, token):
    if token:
        return token
    if not (user and password):
        sys.exit("需要 QL_TOKEN, 或 QL_USER/QL_PASS / --user --pass")
    d = req(url, "/api/user/login", body={"username": user, "password": password})
    return d["data"]["token"]


def summarize(text, tail=110):
    """返回 (结果, 首个错误行)。结果只认日志尾部的 ## 完成 / ## 失败。"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    outcome = "?"
    for l in lines[-4:]:
        if OUT_FAIL in l:
            outcome = "FAIL"
            break
        if OUT_OK in l:
            outcome = "OK"
            break
    err = ""
    for l in lines:
        if OUT_OK in l or OUT_FAIL in l:
            continue
        if ERR_RE.search(l):
            err = l[:tail]
            break
    return outcome, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("QL_URL", "http://192.168.50.1:6700"))
    ap.add_argument("--user", default=os.environ.get("QL_USER"))
    ap.add_argument("--pass", dest="password", default=os.environ.get("QL_PASS"))
    ap.add_argument("--match", action="append", default=[],
                    help="按任务名/命令/日志目录名模糊匹配(可多次)")
    ap.add_argument("--dirs", nargs="*", default=[], help="直接指定日志目录名")
    ap.add_argument("--last", type=int, default=8, help="每个目录只看最近 N 份(默认 8)")
    a = ap.parse_args()

    tok = get_token(a.url, a.user, a.password, os.environ.get("QL_TOKEN"))

    crons = req(a.url, "/api/crons?search=&t=1", tok)["data"]["data"]
    kw = [k.lower() for k in a.match]
    tasks = [c for c in crons
             if not kw or any(k in ((c.get("name") or "") + (c.get("command") or "")).lower()
                              for k in kw)]
    print("== 任务存在性 ==")
    for c in tasks:
        print(f"  id={c['id']:<6} dis={c['isDisabled']} {c['name']:<24} {c['command']:<34} {c['schedule']}")
    if not tasks:
        print("  (没有匹配的任务 — 用 --match 换成名字片段重试)")

    wanted = set(a.dirs)
    for c in tasks:
        cmd = (c.get("command") or "").split()
        if len(cmd) > 1:
            base = os.path.basename(cmd[1].replace("\\", "/"))
            wanted.add(os.path.splitext(base)[0])
            wanted.add(cmd[1].replace("/", "_"))

    dirs = req(a.url, "/api/logs", tok)["data"]
    dirs = dirs if isinstance(dirs, list) else dirs.get("data", [])
    print("\n== 逐日时间线 ==")
    for d in dirs:
        key = d.get("key") or ""
        if wanted and not any(w and (w in key or key in w) for w in wanted):
            continue
        files = sorted([c["title"] for c in (d.get("children") or [])])[-a.last:]
        if not files:
            continue
        print(f"\n[{key}]")
        for f in files:
            q = urllib.parse.quote(f"{key}/{f}")
            try:
                body = req(a.url, "/api/logs/detail?file=" + q, tok)["data"]
            except Exception as e:  # 单份读失败不该中断整条时间线
                print(f"  {f[:23]}  <read failed: {e}>")
                continue
            text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
            outcome, err = summarize(text)
            print(f"  {f[:23]}  {outcome:<5} {err}")
    print("\n判读: 时间线里 OK→FAIL 的那一天就是故障起点; 拿那条错误去对症, "
          "别把「连着失败」讲成「任务被删」。")


if __name__ == "__main__":
    main()
