#!/usr/bin/env python3
# coding: utf-8
"""YYB-Go 微信登录态巡检（阿维塔 / 捷停车 签到前置体检）

为什么要有这个：YYB-Go 的微信登录态约 25-30 天失效一次，失效后
阿维塔日志只写「连不上 YYB-Go … HTTP Error 502」、捷停车静默 0/1，
面板上任务仍是「启用/空闲」，很容易连续几天没人发现。

判据（三层，任一层坏就报）：
  1. YYB-Go /health 不通            → 服务层
  2. /accounts 里目标 openid 不是 alive，或 /wxapp/getCode 返回 502 → 凭据层（需重扫码）
  3. thirdLogin 拿不到 loginToken   → 该微信未绑定阿维塔账号（需先在小程序登录一次）

行为：正常→完全静默（只打印一行 OK）；异常→推 Telegram（面板同一 bot），
每次运行都会再推一遍，直到修好。所有错误码/状态都打印，凭证本体不打印。

用法：
  python3 yyb_watch.py            # 体检，异常才推送
  python3 yyb_watch.py --json     # 只输出一行 JSON（供 Hermes cron 复用）
  python3 yyb_watch.py --no-push  # 体检但不推送
  python3 yyb_watch.py --force-push  # 强制推一条（测试通道用）
"""
import base64, hashlib, json, os, re, sys, time, uuid
import urllib.parse, urllib.request, urllib.error

AVATR_CFG = "/ql/data/scripts/config.json"
JESTING_CFG = "/ql/data/scripts/jesting/config.json"
CRED = "/ql/data/scripts/.yyb_admin.json"
STATE = "/ql/data/scripts/.yyb_watch_state.json"
QL_CFG = "/ql/data/config/config.sh"
LOGIN_HOST = "https://appserver-view.avatr.com"

RSA_PUB = ("MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCZrdn8zDrN2wk0ey3fOy9Arisr5RbqT6bAda3"
           "rwtf8dz1XdjGpCp6BXtJIhgKR1Xj7/0gQwB/nykcR5Dycn5C/agXgxJoiBbYlaiYF70H748nPMz"
           "PAPt9vKC4y7lB3oQgst/MOmzdhzWSmH5elU89vzdleULyTvsQAHaS8vG7KLQIDAQAB")

ARGS = set(sys.argv[1:])
JSON_OUT = "--json" in ARGS
NO_PUSH = "--no-push" in ARGS
FORCE_PUSH = "--force-push" in ARGS


def out(msg):
    if not JSON_OUT:
        print(msg, flush=True)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def bump_streak(bad):
    """记录/返回连续异常天数（同一自然日多次运行只算一天）"""
    st = load_json(STATE, {}) or {}
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    if bad:
        last = st.get("date")
        if last == today:
            streak = int(st.get("streak", 1))
        elif last == yesterday:
            streak = int(st.get("streak", 0)) + 1
        else:
            streak = 1
    else:
        streak = 0
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump({"date": today, "streak": streak}, f)
    except Exception:
        pass
    return streak


def tg_send(title, body):
    try:
        txt = open(QL_CFG, encoding="utf-8", errors="replace").read()
        tok = re.search(r"export\s+TG_BOT_TOKEN=(['\"]?)([^'\"\n]+)\1", txt)
        uid = re.search(r"export\s+TG_USER_ID=(['\"]?)([^'\"\n]+)\1", txt)
        if not (tok and uid):
            return False, "no tg config"
        data = urllib.parse.urlencode({"chat_id": uid.group(2),
                                       "text": f"{title}\n{body}",
                                       "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen(f"https://api.telegram.org/bot{tok.group(2)}/sendMessage",
                                    data=data, timeout=20) as r:
            resp = r.read().decode("utf-8", "replace")
        return ('"ok":true' in resp), resp[:160]
    except Exception as e:
        return False, str(e)[:160]


def http_json(url, payload=None, headers=None, timeout=30):
    hdr = {"Content-Type": "application/json"}
    if headers:
        hdr.update(headers)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=hdr,
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def gen_sign(method, body_obj):
    from Crypto.Cipher import PKCS1_v1_5
    from Crypto.PublicKey import RSA
    cipher = PKCS1_v1_5.new(RSA.import_key(base64.b64decode(RSA_PUB)))
    expire = int(time.time())
    salt = uuid.uuid4().hex
    secret = base64.b64encode(cipher.encrypt(salt.encode())).decode()
    body_str = (json.dumps(body_obj, separators=(",", ":"), ensure_ascii=False)
                if body_obj is not None else "")
    ctype = "" if method.lower() == "get" else "application/json"
    d = {"expire": expire, "params": [],
         "request": {"body": body_str, "content-type": ctype}, "salt": salt}
    sign = hashlib.sha256(json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return {"x-avatr-sign": sign, "x-avatr-secret": secret, "x-avatr-expire": str(expire)}, body_str


def main():
    problems, details, accounts = [], [], []
    avatr = load_json(AVATR_CFG, {}) or {}
    jesting = load_json(JESTING_CFG, {}) or {}

    server = str(avatr.get("yyb_server") or "http://192.168.50.1:8000").rstrip("/")
    appid = str(avatr.get("appid") or "").strip()
    openids = []
    if avatr.get("openid"):
        openids.append(str(avatr["openid"]).strip())
    for s in (jesting.get("servers") or []):
        oid = str(s).rsplit("/", 1)[-1].strip()
        if oid and oid not in openids:
            openids.append(oid)

    if not openids:
        problems.append("配置里没有 openid（avatr config.json / jesting config.json 都空）")

    # 1. 服务层
    try:
        h = http_json(server + "/health", timeout=15)
        out("health: %s" % json.dumps(h, ensure_ascii=False)[:80])
    except Exception as e:
        problems.append("YYB-Go 服务不通 /health：%s" % str(e)[:120])
        h = None

    if h is not None:
        # 2. 凭据层：登录后台看账号状态
        cred = load_json(CRED, {}) or {}
        user, pwd = cred.get("username"), cred.get("password")
        status_map = {}
        if user and pwd:
            import http.cookiejar
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
            try:
                req = urllib.request.Request(
                    server + "/login", data=json.dumps({"username": user, "password": pwd}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                opener.open(req, timeout=25).read()
                accs = json.loads(opener.open(urllib.request.Request(server + "/accounts"), timeout=25).read())["data"] or []
                for a in accs:
                    status_map[a.get("openid")] = a.get("status")
                    accounts.append({"openid_tail": (a.get("openid") or "")[-6:],
                                     "nickname": a.get("nickname"), "status": a.get("status")})
            except Exception as e:
                problems.append("YYB-Go 后台登录/取账号失败：%s" % str(e)[:120])
        else:
            out("跳过账号状态核对（未配置 %s，getCode 已能判定凭据死活）" % CRED)

        for oid in openids:
            st = status_map.get(oid)
            tag = oid[-6:]
            out("account %s: %s" % (tag, st))
            if st is not None and st != "alive":
                problems.append("账号 %s 状态=%s（需重新扫码）" % (tag, st))

            # 逐号 getCode：非 alive 的号必然 502，先记下
            code = None
            try:
                r = http_json(server + "/wxapp/getCode", {"ref": oid, "app_id": appid}, timeout=40)
                code = ((r.get("data") or {}).get("result") or {}).get("code")
                out("getCode %s: %s" % (tag, "ok len=%d" % len(code) if code else "empty"))
            except urllib.error.HTTPError as e:
                problems.append("账号 %s getCode HTTP %s（凭据失效，需重扫码）" % (tag, e.code))
            except Exception as e:
                problems.append("账号 %s getCode 异常：%s" % (tag, str(e)[:100]))

            # 3. 绑定层：只对阿维塔那个 openid 做 thirdLogin
            if code and oid == str(avatr.get("openid") or "").strip():
                try:
                    body = {"thirdType": 5, "sourceType": "MINI_PROGRAM", "authVerifyField": code}
                    sig, body_str = gen_sign("POST", body)
                    headers = {
                        "APPLICATION": "MINI", "OS": "MINI_PROGRAM", "APP-VERSION": "4.5.14",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/plain, */*", "login-token": "",
                        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                       "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 "
                                       "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
                                       "MiniProgramEnv/Windows WindowsWechat"),
                        "Referer": f"https://servicewechat.com/{appid}/99/page-frame.html",
                        **sig,
                    }
                    import requests
                    resp = requests.post(f"{LOGIN_HOST}/api/auth/thirdLogin", headers=headers,
                                         data=body_str.encode(), timeout=25).json()
                    lt = ((resp.get("result") or {}).get("loginToken") or "")
                    bind = (resp.get("result") or {}).get("bindAccountFlag")
                    out("thirdLogin: code=%s token_len=%d bind=%s" % (resp.get("code"), len(lt), bind))
                    if resp.get("code") == 0 and len(lt) < 20:
                        problems.append(
                            "微信 %s 换不出阿维塔登录凭证（bindAccountFlag=%s）："
                            "该微信未绑定阿维塔账号，先用它打开阿维塔小程序/App 登录并手动签到一次"
                            % (oid[-6:], bind))
                except Exception as e:
                    problems.append("thirdLogin 探测异常：%s" % str(e)[:120])

    ok = not problems
    streak = bump_streak(not ok)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    if ok:
        msg = "✅ YYB-Go 与微信绑定态正常（%s）— 阿维塔/捷停车可正常签到" % stamp
        out(msg)
        if FORCE_PUSH and not NO_PUSH:
            okp, r = tg_send("YYB-Go 巡检(测试)", msg)
            out("tg: %s %s" % (okp, r))
    else:
        title = "⚠️ YYB-Go 登录态异常：阿维塔/捷停车签到已挂"
        body = ("时间: %s\n问题:\n%s\n\n处置:\n1) 找 Hermes 生成新二维码，用绑了阿维塔的那个微信扫；"
                "扫完由 agent 调 /qr/confirm\n"
                "2) 若扫上去仍换不出凭证 → 该微信先在阿维塔小程序登录并手动签到一次\n"
                "3) 修好后本巡检会自动静默" % (
                    stamp, "\n".join("· " + p for p in problems)))
        out("PROBLEM: " + " | ".join(problems))
        if not NO_PUSH:
            okp, r = tg_send(title, body)
            out("tg: %s %s" % (okp, r))

    if JSON_OUT:
        print(json.dumps({"ok": ok, "problems": problems, "accounts": accounts,
                          "slot": stamp}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("yyb_watch 异常: %s: %s" % (type(e).__name__, e))
        sys.exit(0)   # 不让青龙把巡检自身记为失败
