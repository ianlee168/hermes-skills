"""Binance 现货小额实盘执行器：硬风控写死在代码里。

凭据：D:\\hermes-test\\.bnb_key.json  {"key": "...", "secret": "..."}
（key 需 IP 白名单=本机出口 IP，权限=允许读取+允许现货交易，禁提现）

用法：
  python binance_spot_executor.py balance
  python binance_spot_executor.py price DOGEUSDT
  python binance_spot_executor.py buy DOGEUSDT 11 --tp 0.06 --sl 0.03
  python binance_spot_executor.py open [SYMBOL]
  python binance_spot_executor.py cancel SYMBOL <orderId>
  python binance_spot_executor.py cancel-oco SYMBOL <orderListId>

风控（改这里，别在命令行临时放宽）：
  MAX_TRADE_USD      单笔成本上限
  MAX_POSITIONS      并行笔数（每笔占两腿：TP + SL）
  DAILY_LOSS_LIMIT   当日已实现净亏熔断（USD）
"""
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.binance.com"
KEYFILE = r"D:\hermes-test\.bnb_key.json"

MAX_TRADE_USD = 157.0
MAX_POSITIONS = 2
HARD_STOP_PCT = 0.03
DAILY_LOSS_LIMIT = 5.0

def creds():
    c = json.load(open(KEYFILE))
    return c["key"], c["secret"]

def req(method, path, params=None, signed=False):
    params = dict(params or {})
    headers = {}
    if signed:
        k, s = creds()
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(s.encode(), qs.encode(), hashlib.sha256).hexdigest()
        headers["X-MBX-APIKEY"] = k
        url = f"{BASE}{path}?{qs}&signature={sig}"
    else:
        k, _ = creds()
        if path.startswith(("/api/v3/account", "/api/v3/order", "/api/v3/myTrades", "/api/v3/openOrders")):
            headers["X-MBX-APIKEY"] = k
        url = f"{BASE}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    r = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return {"error": json.loads(body), "status": e.code}
        except Exception:
            return {"error": body, "status": e.code}

def free_assets():
    acc = req("GET", "/api/v3/account", signed=True)
    if "error" in acc:
        return acc
    return {b["asset"]: round(float(b["free"]), 8) for b in acc["balances"] if float(b["free"]) > 0}

def usdt_free():
    a = free_assets()
    return 0.0 if "error" in a else a.get("USDT", 0.0)

def price(symbol):
    return float(req("GET", "/api/v3/ticker/price", {"symbol": symbol})["price"])

def open_orders(symbol=None):
    params = {"symbol": symbol} if symbol else {}
    return req("GET", "/api/v3/openOrders", params, signed=True)

def day_realized_pnl(symbols):
    """当日已实现盈亏近似：当日 SELL 计入 +quote，BUY 计入 -quote（跨币种需按币种分别算）"""
    day0 = int(time.time() // 86400 * 86400 * 1000)
    pnl = 0.0
    for sym in symbols:
        trades = req("GET", "/api/v3/myTrades", {"symbol": sym, "limit": 200}, signed=True)
        if isinstance(trades, dict) and "error" in trades:
            continue
        for t in trades:
            if t["time"] < day0:
                continue
            q = float(t["quoteQty"])
            pnl += -q if t["isBuyer"] else q
    return pnl

def buy(symbol, quote_usd, tp=0.06, sl=HARD_STOP_PCT):
    quote_usd = float(quote_usd)
    if quote_usd > MAX_TRADE_USD:
        return {"refused": f"单笔 {quote_usd} > 上限 {MAX_TRADE_USD}"}
    op = open_orders()
    if isinstance(op, list) and len(op) >= MAX_POSITIONS * 2:
        return {"refused": f"未平订单 {len(op)} 腿，达并行上限 {MAX_POSITIONS} 笔"}
    if day_realized_pnl([symbol]) <= -DAILY_LOSS_LIMIT:
        return {"refused": f"当日已实现亏损触及熔断 {DAILY_LOSS_LIMIT} USD"}
    if usdt_free() < quote_usd:
        return {"refused": "USDT 可用不足"}

    o = req("POST", "/api/v3/order", {"symbol": symbol, "side": "BUY", "type": "MARKET",
                                     "quoteOrderQty": f"{quote_usd:.2f}"}, signed=True)
    if "error" in o:
        return {"buy_failed": o}

    qty = float(o["executedQty"])
    fills = o.get("fills") or []
    px = (sum(float(f["price"]) * float(f["qty"]) for f in fills) / qty) if fills else price(symbol)
    tp_px = round(px * (1 + float(tp)), 8)
    sl_trig = round(px * (1 - float(sl)), 8)
    sl_limit = round(px * (1 - float(sl) - 0.005), 8)

    oco = req("POST", "/api/v3/order/oco", {
        "symbol": symbol, "side": "SELL", "quantity": f"{qty:.8f}",
        "price": f"{tp_px:.8f}", "stopPrice": f"{sl_trig:.8f}",
        "stopLimitPrice": f"{sl_limit:.8f}", "stopLimitTimeInForce": "GTC"}, signed=True)

    return {
        "entry": {"orderId": o.get("orderId"), "qty": qty, "avgPrice": px,
                  "quoteQty": float(o.get("cummulativeQuoteQty", 0))},
        "exit_oco": {"orderListId": (oco or {}).get("orderListId"),
                     "tp": tp_px, "sl_trigger": sl_trig, "sl_limit": sl_limit,
                     "error": (oco or {}).get("error")},
        "max_loss_usd": round(qty * (px - sl_trig), 4),
        "verify": "回读 open(orders) 确认两腿都在；再读 myTrades 看手续费",
    }

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "balance"
    if cmd == "balance":
        print(json.dumps({"free": free_assets(), "usdt_free": usdt_free()}, ensure_ascii=False, indent=1))
    elif cmd == "price":
        print(json.dumps({"symbol": sys.argv[2], "price": price(sys.argv[2])}))
    elif cmd == "open":
        sym = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(open_orders(sym), ensure_ascii=False, indent=1))
    elif cmd == "buy":
        sym, usd = sys.argv[2], float(sys.argv[3])
        tp, sl = 0.06, HARD_STOP_PCT
        if "--tp" in sys.argv:
            tp = float(sys.argv[sys.argv.index("--tp") + 1])
        if "--sl" in sys.argv:
            sl = float(sys.argv[sys.argv.index("--sl") + 1])
        print(json.dumps(buy(sym, usd, tp, sl), ensure_ascii=False, indent=1))
    elif cmd == "cancel":
        print(json.dumps(req("DELETE", "/api/v3/order", {"symbol": sys.argv[2], "orderId": sys.argv[3]}, signed=True),
                         ensure_ascii=False, indent=1))
    elif cmd == "cancel-oco":
        print(json.dumps(req("DELETE", "/api/v3/orderList", {"symbol": sys.argv[2], "orderListId": sys.argv[3]}, signed=True),
                         ensure_ascii=False, indent=1))
    else:
        print("usage: balance|price SYM|open [SYM]|buy SYM USD [--tp 0.06] [--sl 0.03]|cancel SYM ID|cancel-oco SYM LISTID")

if __name__ == "__main__":
    main()
