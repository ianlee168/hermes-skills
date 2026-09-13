#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
米家门锁摄像头的云端抓拍取图（门铃那一帧）
------------------------------------------------
依赖: pip install micloud pycryptodome
环境: HASS_URL / HASS_TOKEN（HA 长令牌）；MI_AUTH_FILE 指向米家云鉴权缓存
用法: python mi_snapshot.py [--all] [--hours 24] [--out last_door.jpg]
"""
import argparse
import base64
import glob
import hashlib
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

from micloud import miutils

HA = os.environ.get("HASS_URL", "http://homeassistant.local:8123").rstrip("/")
TOKEN = os.environ.get("HASS_TOKEN", "")
AUTH_FILE = os.environ.get("MI_AUTH_FILE", "")
LOCK_DID = os.environ.get("LOCK_DID", "")
LOCK_MODEL = os.environ.get("LOCK_MODEL", "xiaomi.lock.s1")
LOCK_ENTITY = os.environ.get("LOCK_ENTITY", "")
HERE = os.path.dirname(os.path.abspath(__file__))


def all_auths():
    base = os.path.dirname(AUTH_FILE)
    out = []
    for f in sorted(glob.glob(os.path.join(base, "auth-*-cn*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))["data"]
            if d.get("ssecurity") and d.get("service_token"):
                out.append((os.path.basename(f), d["ssecurity"], d["service_token"]))
        except Exception:
            pass
    out.sort(key=lambda x: 0 if x[0].endswith("-cn.json") else 1)   # xiaomiio 优先
    return out


def ha_service(service, body):
    req = urllib.request.Request(
        f"{HA}/api/services/{service}?return_response=true",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode()).get("service_response")


def events(did=LOCK_DID, model=LOCK_MODEL, hours=24, limit=5):
    api = "https://business.smartcamera.api.io.mi.com/common/app/get/eventlist"
    now = int(time.time() * 1000)
    data = {"did": did, "model": model, "doorBell": "true", "eventType": "Default",
            "needMerge": True, "sortType": "DESC", "region": "CN", "language": "zh_CN",
            "beginTime": now - hours * 3600 * 1000, "endTime": now + 999, "limit": limit}
    res = ha_service("xiaomi_miot/request_xiaomi_api",
                     {"entity_id": LOCK_ENTITY, "api": api, "data": data,
                      "method": "GET", "crypt": True})
    return ((res or {}).get("data") or {}).get("thirdPartPlayUnits") or []


def sha1_sign(method, url, dat, nonce):
    path = urllib.parse.urlparse(url).path
    if path[:5] == "/app/":
        path = path[4:]
    arr = [method.upper(), path] + [f"{k}={v}" for k, v in dat.items()] + [nonce]
    return base64.b64encode(hashlib.sha1("&".join(arr).encode("utf-8")).digest()).decode()


def rc4_url(url, params, ssecurity):
    nonce = miutils.gen_nonce()
    sn = miutils.signed_nonce(ssecurity, nonce)
    p = {k: str(v) for k, v in params.items()}
    p["rc4_hash__"] = sha1_sign("GET", url, p, sn)
    p = {k: miutils.encrypt_rc4(sn, v) for k, v in p.items()}
    p["signature"] = sha1_sign("GET", url, p, sn)
    p["ssecurity"] = ssecurity
    p["_nonce"] = nonce
    return url + "?" + urllib.parse.urlencode(p)


def image_bytes(file_id, img_store_id):
    """取回 JPEG；两份云鉴权都试，返回的是 AES 加密的就解一下"""
    from Crypto.Cipher import AES
    url = "https://processor.smartcamera.api.io.mi.com/miot/camera/app/v1/img"
    last = None
    for tag, ssecurity, service_token in all_auths():
        iv = bytes(random.getrandbits(8) for _ in range(16))
        data = json.dumps({"did": LOCK_DID, "fileId": str(file_id), "stoId": img_store_id,
                           "segmentIv": base64.b64encode(iv).decode()}, separators=(",", ":"))
        full = rc4_url(url, {"data": data}, ssecurity) + "&yetAnotherServiceToken=" + service_token
        req = urllib.request.Request(full, headers={"User-Agent": "MiHome/6.0.0 (com.xiaomi.smarthome)"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
        except Exception as e:
            last = f"{tag}: {e}"
            continue
        key = base64.b64decode(ssecurity)
        if len(key) not in (16, 24, 32):
            key = hashlib.sha256(key).digest()
        blob = raw
        if blob[:2] != b"\xff\xd8":
            try:
                body = raw[: len(raw) - (len(raw) % 16)]
                blob = AES.new(key, AES.MODE_CBC, iv).decrypt(body)
            except Exception as e:
                last = f"{tag} AES: {e}"
                continue
        if blob[:2] == b"\xff\xd8":
            return blob
        last = f"{tag}: 既不是 JPEG 也不是可解密的密文 {raw[:8]!r}"
    raise RuntimeError("取图失败: " + str(last))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--out", default=os.path.join(HERE, "last_door.jpg"))
    a = ap.parse_args()
    units = events(hours=a.hours)
    print(f"门锁云端事件 {len(units)} 条")
    for u in units:
        ts = time.strftime("%m-%d %H:%M:%S", time.localtime((u.get("createTime") or 0) / 1000))
        kinds = ",".join(str(d.get("event")) for d in (u.get("eventTypeDetail") or []))
        print(f"  {ts}  {u.get('eventType')}  [{kinds}]  有图={bool(u.get('imgStoreId'))}")
    if a.all:
        return
    bell = fb = None
    for u in units:
        for d in (u.get("eventTypeDetail") or []):
            if not d.get("imgStoreId"):
                continue
            if d.get("event") == "Bell":
                bell = bell or (u, d)
            elif fb is None:
                fb = (u, d)
    u, det = bell or fb or (None, None)
    if not u:
        print("没有带图的事件")
        sys.exit(1)
    img = image_bytes(u.get("fileId"), det.get("imgStoreId"))
    open(a.out, "wb").write(img)
    print(f"已保存 {a.out}  ({len(img)} 字节, 事件={det.get('event')})")


if __name__ == "__main__":
    main()
