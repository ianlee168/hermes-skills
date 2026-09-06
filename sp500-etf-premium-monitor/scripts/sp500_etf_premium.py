#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标普500 ETF 溢价率监控 (513650 南方 / 159612 国泰 / 513500 博时)

由 Hermes cron 在每个交易日 09:35(开市) 与 15:05(收市) 调用 (no_agent 模式)。

行为:
  - 交易日: 生成全量报告, 固定发一条微信 (报告内含 🔴/⚠️ 提醒行)
  - 任一溢价率 < 3%: 额外弹 Windows 弹窗强提醒 (每天最多一次)
  - 发送失败自动重试 (等 45s x 5 次); 10 分钟内已发过则去重 (catch-up 补跑)
  - cron deliver=local (2026-09-06 起): 引擎不再投递, 微信由本脚本独家发送,
    彻底避开 引擎投递 + 启动通知/群发补跑 连发撞 iLink 限流 的问题
  - 非交易日 (行情时间戳不是今天): 静默退出, 不发微信; 设 HERMES_SP500_DRY=1 可演练不发

口径: 溢价率 = (场内现价 - 最新单位净值) / 最新单位净值 × 100
(最新单位净值即 QDII 前一日净值, 用户 7/28 记录 3.62% 验证口径一致)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CODES = [  # (secid, code, name)
    ("1.513650", "513650", "标普500ETF南方"),
    ("0.159612", "159612", "标普500ETF国泰"),
    ("1.513500", "513500", "标普500ETF博时"),
]
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "sp500_etf_premium_state.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/120 Safari/537.36")
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
ANDROID_UA = "Mozilla/5.0 (Linux; Android 10)"


def decode_bytes(raw):
    """腾讯行情是 GBK, eastmoney 各 API 是 UTF-8: UTF-8 优先, GBK 兜底."""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def fetch(url, timeout=20, ua=None, referer="https://fund.eastmoney.com/"):
    """原生 Windows 进程里执行 curl.exe (schannel). eastmoney push2 对本机不稳,
    现价用腾讯、净值用 fundmobapi 均为稳定通道; 仍保留 2 次重试.
    fundmobapi 只认 Android 手机 UA (桌面 UA 返回网络繁忙)."""
    curl = shutil.which("curl") or r"C:\Windows\System32\curl.exe"
    headers = ["-H", f"User-Agent: {ua or UA}",
               "-H", f"Referer: {referer}"]
    last = ""
    for attempt in range(2):
        try:
            r = subprocess.run(
                [curl, "-sS", "--max-time", str(timeout)] + headers + [url],
                capture_output=True, timeout=timeout + 10)
            if r.returncode == 0 and r.stdout:
                return decode_bytes(r.stdout)
            last = r.stderr.decode("utf-8", "replace")[:200] or f"rc={r.returncode}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(2)
    raise RuntimeError(f"curl 请求失败: {last}")


def get_shen_gou_status(code):
    """从基金运作公告判断当前申购状态 (开放/暂停申购).

    规则: 取 type=5 运作公告中最新一条「暂停申购/恢复申购」标题决定;
    排除 节假日安排/单日暂停(标题含完整日期)/代办券商/支付渠道 等非持续状态.
    无相关公告 → 默认开放申购.
    """
    url = ("https://api.fund.eastmoney.com/f10/JJGG"
           f"?fundcode={code}&pageIndex=1&pageSize=50&type=5")
    try:
        d = json.loads(fetch(url, ua=UA,
                             referer=f"https://fundf10.eastmoney.com/jjgg_{code}_1.html"))
    except Exception as e:  # noqa: BLE001
        return f"未知({str(e)[:30]})"
    skip = re.compile(r"节假日|安排|券商|代办|支付|通联|转换|定额|货币基金|\d{4}年\d{1,2}月\d{1,2}日")
    best = None  # (pubdate, id, kind)
    for it in d.get("Data") or []:
        t = it.get("TITLE") or ""
        if skip.search(t):
            continue
        if "恢复申购" in t:
            kind = "open"
        elif "暂停申购" in t:
            kind = "suspend"
        else:
            continue
        key = (it.get("PUBLISHDATE") or "", it.get("ID") or "")
        if best is None or key > best[0]:
            best = (key, kind, t)
    if best is None:
        return "开放申购"
    kind = best[1]
    t = best[2]
    if kind == "suspend":
        return "暂停大额申购" if "大额" in t else "暂停申购"
    return "开放申购"


def get_quotes():
    """现价/涨跌幅/行情时间来自腾讯 qt.gtimg.cn (Windows 下比 eastmoney push2 稳)."""
    syms = {"sh513650": "513650", "sz159612": "159612", "sh513500": "513500"}
    url = "https://qt.gtimg.cn/q=" + ",".join(syms)
    text = fetch(url)
    out = {}
    for line in text.split(";"):
        line = line.strip()
        if '="' not in line:
            continue
        val = line.split('="', 1)[1].rstrip('"')
        f = val.split("~")
        if len(f) < 40 or not f[2]:
            continue
        try:
            price = float(f[3])
            chg = float(f[32]) if f[32] else None
        except ValueError:
            continue
        out[f[2]] = {
            "price": price,
            "chg": chg,
            "name": f[1],
            "ts": f[30],  # YYYYMMDDHHMMSS
        }
    return out


def get_nav(code):
    """最新单位净值 + 净值日期, 失败抛异常."""
    url = ("https://fundmobapi.eastmoney.com/FundMNewApi/"
           f"FundMNBasicInformation?FCODE={code}"
           "&deviceid=Wap&plat=Wap&product=EFund&version=6.2.8")
    d = json.loads(fetch(url, ua=ANDROID_UA))["Datas"]
    return float(d["DWJZ"]), d["FSRQ"]


def send_weixin(text, max_attempts=4):
    """iLink 有限流熔断: 失败按指数退避重试 [60s, 180s, 420s].

    2026-09-06 实测: hermes send 非 --json 模式失败时静默退出码 1, 错误只在
    --json 输出里; 且 iLink 风控时每次失败都会重置 30s 冷却, 固定间隔重试
    永远等不到头 -> 必须退避. 成功返回 True.
    """
    exe = os.environ.get("HERMES_BIN") or shutil.which("hermes") or "hermes"
    delays = (60, 180, 420)
    err = "unknown"
    for attempt in range(1, max_attempts + 1):
        try:
            r = subprocess.run([exe, "send", "-t", "weixin", "--json", text],
                               timeout=30, capture_output=True)
            out = (r.stdout or b"").decode("utf-8", "replace")
            try:
                info = json.loads(out) if out.strip() else {}
            except Exception:  # noqa: BLE001
                info = {}
            if r.returncode == 0 and not info.get("error"):
                return True
            err = (info.get("error") or out.strip()[:200]
                   or (r.stderr or b"").decode("utf-8", "replace")[:200]
                   or f"rc={r.returncode}")
        except Exception as e:  # noqa: BLE001
            err = str(e)
        if attempt < max_attempts:
            time.sleep(delays[attempt - 1])
    print(f"[warn] 微信发送失败({max_attempts}次): {err}", file=sys.stderr)
    return False


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_state(patch_dict):
    st = load_state()
    st.update(patch_dict)
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception:  # noqa: BLE001
        pass


def popup(title, text):
    """Windows: PowerShell 弹窗; 其他平台 (Ubuntu server 无 GUI): 跳过.
    强提醒本身已通过微信送达, 弹窗只是本机补充."""
    if not sys.platform.startswith("win"):
        print(f"[info] 非 Windows, 跳过弹窗: {title}", file=sys.stderr)
        return
    escaped = text.replace("'", "''")
    cmd = ("Add-Type -AssemblyName System.Windows.Forms; "
           f"[System.Windows.Forms.MessageBox]::Show('{escaped}',"
           f"'{title}','OK','Warning') | Out-Null; "
           "[console]::beep(1200,800)")
    try:
        subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-WindowStyle", "Hidden", "-Command", cmd],
                       timeout=30, capture_output=True)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 弹窗失败: {e}", file=sys.stderr)


def popup_done_today():
    return load_state().get("popup_date") == datetime.date.today().isoformat()


def mark_popup_done():
    save_state({"popup_date": datetime.date.today().isoformat()})


def send_dedup_ok():
    """距上次成功微信发送 <10 分钟则不重复发.

    台式机常错过 09:35/15:05 计划时刻, 登录后 open+close 会成对补跑
    (曾 21:21 两任务同时补跑 -> 连发限流). 正常在线时两次播报间隔
    5.5h 不受影响; 成对补跑时只发第一条, 第二条仅写本地日志.
    """
    try:
        last = load_state().get("last_send_ts") or 0
    except Exception:  # noqa: BLE001
        last = 0
    return time.time() - last >= 600


def main():
    force = "--force" in sys.argv
    now = datetime.datetime.now()
    session = "开市" if now.hour < 12 else "收市"

    # ---- 1. 拉行情 ----
    try:
        quotes = get_quotes()
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 标普500ETF监控: 行情接口失败\n{e}\n"
              f"(监控脚本 sp500_etf_premium.py 需检查)")
        return

    # ---- 2. 非交易日检测 (腾讯行情时间戳不是今天) ----
    today = now.date().isoformat().replace("-", "")
    if not force:
        stale = True
        for q in quotes.values():
            ts = str(q.get("ts") or "")
            if len(ts) >= 8 and ts[:8] == today:
                stale = False
                break
        if stale:
            return  # 非交易日: 静默退出, no_agent 模式不投递

    # ---- 3. 拉净值 + 申购状态 + 算溢价率 ----
    rows = []
    for secid, code, _name in CODES:
        q = quotes.get(code, {})
        try:
            nav, fsrq = get_nav(code)
        except Exception as e:  # noqa: BLE001
            rows.append({"code": code, "name": q.get("name", _name),
                         "price": q.get("price"), "chg": q.get("chg"),
                         "nav": None, "fsrq": None, "prem": None,
                         "sgzt": None, "err": str(e)[:80]})
            continue
        price = q.get("price")
        prem = (price - nav) / nav * 100 if price is not None and nav else None
        rows.append({"code": code, "name": q.get("name", _name),
                     "price": price, "chg": q.get("chg"), "nav": nav,
                     "fsrq": fsrq, "prem": prem,
                     "sgzt": get_shen_gou_status(code), "err": None})

    # ---- 4. 组装报告 ----
    lines = [f"📊 标普500ETF溢价率监控 · {now:%m/%d %H:%M} {session}",
             "", "| 代码 | 名称 | 现价 | 今日% | 单位净值(日) | 申购 | 溢价率 |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["prem"] is None:
            lines.append(f"| {r['code']} | {r['name']} | {r['price'] or '--'} "
                         f"| -- | 净值获取失败 | -- | {r['err']} |")
            continue
        flag = "🔴" if r["prem"] < 3 else ("⚠️" if r["prem"] < 5 else "🟢")
        nav_d = r["fsrq"][5:].replace("-", "/") if r["fsrq"] else "--"
        chg = f"{r['chg']:+.2f}" if isinstance(r["chg"], (int, float)) else "--"
        sg = r.get("sgzt") or "--"
        sg = "🔒" + sg if sg.startswith("暂停") else ("✅" + sg if sg == "开放申购" else sg)
        lines.append(f"| {r['code']} | {r['name']} | {r['price']:.3f} | {chg}% "
                     f"| {r['nav']:.4f}({nav_d}) | {sg} | {flag} {r['prem']:+.2f}% |")

    lows = [r for r in rows if r["prem"] is not None]
    strong = [r for r in lows if r["prem"] < 3]
    general = [r for r in lows if 3 <= r["prem"] < 5]
    suspended = [r for r in lows if (r.get("sgzt") or "").startswith("暂停")
                 and r["prem"] is not None and r["prem"] >= 5]

    if strong:
        names = "、".join(f"{r['name']}({r['prem']:+.2f}%)" for r in strong)
        lines.append("")
        lines.append(f"🔴 **强提醒: {names} 溢价率已低于 3%**, 难得的低溢价机会")
    elif general:
        names = "、".join(f"{r['name']}({r['prem']:+.2f}%)" for r in general)
        lines.append("")
        lines.append(f"⚠️ **一般提醒: {names} 溢价率已低于 5%**, 可关注")
    else:
        lines.append("")
        lines.append("🟢 均高于 5%, 无提醒")
    if suspended:
        names = "、".join(f"{r['name']}({r['prem']:+.2f}%)" for r in suspended)
        lines.append("")
        lines.append(f"ℹ️ {names} 暂停申购中, 溢价短期难被套利抹平")
    report = "\n".join(lines)

    print(report)

    # 本地日志兜底: 即使投递失败也能查历史趋势
    try:
        with open(os.path.join(HERE, "sp500_etf_premium.log"), "a",
                  encoding="utf-8") as f:
            f.write(report.replace("\n\n", "\n") + "\n")
    except Exception:  # noqa: BLE001
        pass

    # ---- 5. 微信例行播报 + 强提醒弹窗 ----
    # 2026-09-06: cron deliver 已改 local, 微信由本脚本独家发送.
    # 全量报告固定发 (含 🔴/⚠️ 提醒行, 不再单独发短消息, 避免一日两条连发);
    # <3% 强提醒时额外弹 Windows 弹窗 (每日最多一次).
    # catch-up 成对补跑时 10 分钟内只发一条; 失败自动重试 (45s x 5).
    if strong and not popup_done_today():
        popup("标普500ETF 溢价率强提醒",
              f"以下ETF溢价率已低于3%:\n" + "\n".join(
                  f"{r['name']} {r['code']} {r['prem']:+.2f}%" for r in strong))
        mark_popup_done()
    if os.environ.get("HERMES_SP500_DRY") == "1":
        print("[dry-run] HERMES_SP500_DRY=1, 跳过微信发送")
    elif send_dedup_ok():
        if send_weixin(report):
            save_state({"last_send_ts": time.time()})
    else:
        print("[skip] 10 分钟内已发过微信 (catch-up 去重), 本次仅本地日志")

if __name__ == "__main__":
    main()