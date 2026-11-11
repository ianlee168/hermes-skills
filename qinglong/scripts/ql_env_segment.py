#!/usr/bin/env python3
# coding: utf-8
"""青龙 env 分段写入助手 —— 凭证永不回显(纯 stdlib)

用法(QL_AUTH 从环境变量注入,别写进命令行历史):
  export QL_AUTH='{"username":"...","password":"..."}'   # 容器: docker exec qinglong cat /ql/data/config/auth.json
  python3 ql_env_segment.py --name JD_WSCK --show
  python3 ql_env_segment.py --name JD_WSCK --add 'pin=xxx;wskey=yyy;'
  python3 ql_env_segment.py --id 20 --value 'pin=a;wskey=b;&pin=c;wskey=d;'
默认 QL_URL=http://192.168.50.1:6700(容器内改成 http://127.0.0.1:5700 或设 QL_URL)

设计要点(踩过的坑都在里面):
 - 只按 pin 做增/换 → 不会误伤同一 env 里的其它账号段
 - **任何输出都不含 value 本体**,只打 pin / wskey 长度 / 段数
 - 写前打旧结构、写后回读复核;响应里的 value 主动 pop 掉
"""
import argparse, json, os, re, ssl, sys, urllib.request


def http(url, data=None, headers=None, method=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def pin_of(seg):
    m = re.search(r"pin=([^;]+)", seg or "")
    return m.group(1) if m else ""


def wskey_len(seg):
    m = re.search(r"wskey=([^;]+)", seg or "")
    return len(m.group(1)) if m else 0


def dump(tag, value):
    segs = [s for s in (value or "").split("&") if s.strip()]
    print("%s: 段数=%d 总长=%d" % (tag, len(segs), len(value or "")))
    for i, s in enumerate(segs, 1):
        print("   段%d pin=%-20s wskey长度=%d 段长=%d" % (i, pin_of(s)[:20], wskey_len(s), len(s)))
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("QL_URL", "http://192.168.50.1:6700"))
    ap.add_argument("--id", type=int, default=0)
    ap.add_argument("--name", default="")
    ap.add_argument("--value", default="", help="整值覆盖(多段用 & 连接,段尾 ;)")
    ap.add_argument("--add", default="", help="只加/换一个账号段,如 'pin=x;wskey=y;'")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()

    auth = os.environ.get("QL_AUTH")
    if not auth:
        sys.exit("需要 QL_AUTH='{\"username\":..,\"password\":..}'")
    cred = json.loads(auth)
    tok = http(a.url + "/api/user/login",
               json.dumps({"username": cred["username"], "password": cred["password"]}).encode(),
               {"Content-Type": "application/json"}, "POST")["data"]["token"]
    H = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}

    envs = http(a.url + "/api/envs?searchValue=", None, H)["data"]
    if a.id:
        cur = next(e for e in envs if e["id"] == a.id)
    else:
        cur = next(e for e in envs if e["name"] == a.name)

    old = cur.get("value") or ""
    segs = dump("写入前 (id=%s name=%s status=%s)" % (cur["id"], cur["name"], cur["status"]), old)

    new = a.value or ""
    if a.add:
        add = a.add if a.add.endswith(";") else a.add + ";"
        p = pin_of(add)
        if not p:
            sys.exit("--add 里没找到 pin=")
        segs = [s for s in segs if pin_of(s) != p] + [add]
        new = "&".join(s.rstrip("&") for s in segs)
    if a.show and not new:
        return
    if not new:
        sys.exit("没给 --add/--value,只做了查看(需要看结构就加 --show)")

    r = http(a.url + "/api/envs", json.dumps({"id": cur["id"], "name": cur["name"], "value": new}).encode(), H, "PUT")
    if isinstance(r, dict):
        r.pop("value", None)
        if isinstance(r.get("data"), dict):
            r["data"].pop("value", None)
    print("写入结果:", json.dumps(r, ensure_ascii=False)[:200])

    after = next(e for e in http(a.url + "/api/envs?searchValue=", None, H)["data"] if e["id"] == cur["id"])
    dump("写入后", after.get("value"))
    print("提示: 若任务读不到新值, 检查 preload 的 mtime 是否与本步同秒(面板写 env 会同步重写 preload)。")


main()
