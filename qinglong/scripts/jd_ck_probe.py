#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预检一条 JD 凭证是否可用 —— 写进 JD_COOKIE 之前跑,避免把死 key 写进面板。

用法（必须从**青龙容器内**跑，与任务同出口 IP；本机跑的结果不代表面板结果）:

  scp jd_ck_probe.py root@<nas>:/mnt/user/appdata/qinglong/scripts/
  ssh root@<nas> 'docker exec -i qinglong python3 /ql/data/scripts/jd_ck_probe.py "pt_key=..;pt_pin=..;"'
  ssh root@<nas> 'docker exec -i qinglong python3 /ql/data/scripts/jd_ck_probe.py "AAJq..." --pin jd_xxxx'

退出码: 0=有效  1=凭证无效  2=入参问题  3=网络/端点问题（不能据此判死活）

凭证形态（不要互相加/去前缀，原样用）:
  75 位 AAJq...            = 网页版 / H5(m.jd.com) 的 pt_key
  83 位 app_openAAJq...    = App 接口换出来的 pt_key
  给 75 位的串硬加 `app_open` 前缀会得到 1001 not login，反之亦然。
"""
import json
import ssl
import sys
import urllib.request

API = "https://me-api.jd.com/user_new/info/GetJDUserInfoUnion"
UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2

    raw = args[0]
    pin = args[args.index("--pin") + 1] if "--pin" in args else None

    key = None
    for part in raw.replace("\n", ";").split(";"):
        part = part.strip()
        if part.startswith("pt_key="):
            key = part[len("pt_key="):].strip()
        elif part.startswith("pt_pin="):
            pin = part[len("pt_pin="):].strip()

    if not key:
        print("✗ 没解析到 pt_key")
        return 2
    if not pin:
        print("✗ 没解析到 pt_pin，补 --pin <pin>")
        return 2

    form = "App版(app_open)" if key.startswith("app_open") else "网页版"
    print(f"凭证形态: {form}  长度={len(key)}  pin={pin[:6]}***")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(API, headers={
        "Cookie": f"pt_key={key};pt_pin={pin};",
        "User-Agent": UA,
        "Referer": "https://home.m.jd.com/myJd/newhome.action",
    })
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
    except Exception as exc:  # noqa: BLE001 - 网络问题不能当凭证结论
        print(f"✗ 请求失败（网络/端点问题，不能据此判凭证死活）: {exc}")
        return 3

    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        print(f"✗ 返回非 JSON(status={status})，端点可能被挡，不能据此判死活")
        return 3

    if data.get("retcode") == "1001" or data.get("msg") == "not login":
        print("✗ 凭证无效（1001 not login）")
        return 1

    payload = data.get("data") or {}
    nick = ((payload.get("userInfo") or {}).get("nickname")
            or (payload.get("baseInfo") or {}).get("nickname")
            or "?")
    print(f"✓ 凭证有效  昵称={nick}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
