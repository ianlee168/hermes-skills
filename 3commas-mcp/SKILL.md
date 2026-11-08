---
name: 3commas-mcp
description: Use when driving 3commas via MCP/REST or auditing plan.
version: 1.1.0
author: 110妹
license: MIT
platforms: [windows, linux, macos]
tags: [3commas, mcp, api, trading-bots, binance]
metadata:
  hermes:
    tags: [3commas, mcp, api, trading-bots, binance]
    triggers: ["3commas MCP", "3commas API", "3commas 工具", "开仓", "平仓", "策略", "机器人", "get_live_strategies", "place_strategy_trade", "订阅套餐"]
---

# 3commas MCP / REST API

## When to Use

- 要让 agent 直接看/管 3commas 账户（连接、余额、策略、历史），而不是点网页。
- 用户问“3commas 有没有 skill / 能不能你自己操作账户 / 帮我开个仓”。
- 要评估 3commas 套餐能不能跑实盘。
- 网页端 API 页创建 MCP key、或 MCP 连接报错时排障。

配对 skill：`exchange-api-connectivity`（交易所 API key 连不上、IP 白名单）。

## 服务端点（官方，2026-11 实测）

- MCP：`https://mcp.trade.3commas.io/mcp`（老文档里还有 `https://trade.3commas.io:2083/mcp`，优先前者）
- 鉴权：HTTP 头 `X-API-Key` + `X-Secret-Key`（不是 Bearer）
- REST 文档：`https://trade.3commas.io/docs/rest-api`；MCP 文档：`https://trade.3commas.io/docs/mcp`
- 服务自报 `3commas-tools`，2026-11 版本 1.1.0，**17 个工具**

## 1. 建 3commas API key（网页）

页面：`https://trade.3commas.io/zh/trader/open_api` → 「创建 API 密钥」。

- 表单仅三项：**名称 / 权限 / IP**。权限是 5 组 ×（读取/写入）：`API 配置`、`策略`、`信号机器人`、`定投机器人`、`网格机器人`。
- **只读起步**：只勾 5 个「读取」。要能开平仓才需要 `策略: 写入`。
- **3commas 的 key 没有「编辑」，加权限只能新建一把**（上限 10 把）。
- **创建时权限下拉默认全选**（占位符显示「所有权限」）：打开后必须把不要的逐个取消，再回读 `checked` 校正。复选框是原生 `input[type=checkbox]`，DOM 顺序是 `读,写,读,写...` 成对；按索引盲点会把「写入」打开（实测踩过）。
- **IP 留空 = key 三个月后自动过期删除；填了 IP = 永不过期，但请求只能从那些 IP 来。** 先 `curl https://api.ipify.org` 取出口 IP（家里是动态 IP，换网/VPN 后回来补）。
- key/secret 只显示一次，弹窗里读进变量/文件，落 gbrain。

## 2. 接到 Hermes（原生 MCP）

```yaml
mcp_servers:
  3commas:
    url: "https://mcp.trade.3commas.io/mcp"
    headers:
      X-API-Key: "<key>"
      X-Secret-Key: "<secret>"
    timeout: 180
```

- 用 `hermes config set mcp_servers.3commas.url ...` / `.headers.X-API-Key` / `.headers.X-Secret-Key` / `.timeout` 逐项写；**需要重启 Hermes 才注册 `mcp_3commas_*` 工具**（无热重载）。
- 需要 `mcp` python 包；换 key 只改这两行 header。

## 3. 不重启也能用：命令行客户端（mcp 2.x API 名已改）

`mcp>=2.3` 的 import 名变了（旧名 `streamablehttp_client` 已不存在）：

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client

http_client = create_mcp_http_client(headers={"X-API-Key": k, "X-Secret-Key": s})
async with streamable_http_client(URL, http_client=http_client) as streams:
    r, w = (streams.read, streams.write) if hasattr(streams, "read") else (streams[0], streams[1])
    async with ClientSession(r, w) as sess:
        init = await sess.initialize()
        si = init.server_info            # 不是 serverInfo
        tools = await sess.list_tools()  # tool.input_schema，不是 inputSchema
        res = await sess.call_tool(name, args)
        for c in res.content: print(getattr(c, "text", ""))
```

- `streamable_http_client()` **没有 `headers=` 参数**，头必须走 `create_mcp_http_client(headers=...)`。
- 现成脚本：`D:\hermes-test\mcp3c.py`（列工具）、`mcp3c_call.py <tool> '<json>'`（调工具）、`mcp3c_schema.py <tool>`（看参数 schema）；凭据读 `D:\hermes-test\.3c_api.json`。

## 4. 工具清单（17）

只读：`get_supported_exchanges`、`get_exchange_markets`（参数是 `{"exchanges":["BINANCE_FUTURES"]}`，**不是** `exchangeCode`）、`get_exchange_families`、`get_api_profiles`、`get_strategy`、`get_live_strategies`、`export_strategies_history`、`export_strategy_orders_history`

写/交易：`create_api_profile`、`edit_api_profile`、`delete_api_profile`、`place_strategy_trade`、`edit_trade_strategy`、`cancel_strategy`、`close_strategy_market`、`place_strategy_market_enter`、`place_strategy_swing`

`get_api_profiles` 每个市场一条：`exchange.code` ∈ `BINANCE`(现货) / `BINANCE_FUTURES`(USDT-M) / `BINANCE_DELIVERY`(COIN-M)，同一连接共享 `masterCode`，`status` 可能是 `active` / `no_assets`，`demo: true` 是模拟盘。

### place_strategy_trade 最少可用参数（实测 2026-11-08）

```json
{"exchangeCode":"BINANCE_FUTURES","pairCode":"BTCUSDT","profilesCodes":["<profile code>"],
 "side":"long","orderType":"market","amountPerTrade":100,"amountPerTradeType":"quote",
 "leverage":1,"takeProfits":[{"portfolio":1,"priceDeviation":0.02}],"stopLoss":0.015}
```

- 必需：`exchangeCode`、`pairCode`、`profilesCodes`、`side`、`orderType`、`amountPerTrade`、`amountPerTradeType`。
- `amountPerTradeType` 枚举：`quote` / `base` / `$` / `percents` / `contracts`。
- **止盈止损都是小数**（2% → `0.02`），传百分数直接校验失败；`takeProfits[].portfolio` 必填且总和 = 1。
- 返回 `tradesDetails[].strategyId` + `status:"new"`；用 `get_live_strategies` / `get_strategy` 回读，`status:"entered"` + `paperTrading:true` 才算真进场。
- **实际入场小于 amountPerTrade**：100 quote 在 BTCUSDT 只成了 0.001 BTC ≈ $75.9（合约步进截断），预期收益按实际 `totalEntryCost` 算。
- `pairCode` 取值：先 `get_exchange_markets {"exchanges":["BINANCE_FUTURES"]}`，用返回的 `code`。

## 5. 套餐（2026-11 官网价）

| 套餐 | 月付 | 年付折后省 | 每个交易所 API | 多API交易 | 信号/定投/网格 |
|---|---|---|---|---|---|
| Free | 0 | — | 1 | 1 | 0 |
| Starter | US$15/月 | 省 $60 | 1 | 1 | 2 / 5 / 2 |
| Pro | US$38/月 | 省 $150 | 5 | 10 | 20 / 20 / 10 |
| Expert | US$105/月 | 省 $420 | 25 | 50 | 1000 |

**Free 套餐不能交易**（手动也不行），只能连交易所看余额。新账号默认 Pro 7 天试用；试用到期降 Free，所以“试用期跑出利润再订阅”只能在试用这几天内做，且真钱单要用户当轮点头。

## 6. 安全盘点必查项

- `设置 → 安全`：`2FA 身份验证状态：已禁用` 是常见默认状态，**开实盘前必须打开**（需用户用验证器 App 扫码）。开启后该行变「已启用」+「禁用」按钮；已有 API key / MCP 不受影响。
- 交易权限的 key 必须配 IP 白名单；交易所侧白名单缺 IP 会导致全部市场认证失败（见 `exchange-api-connectivity`）。
- 老 key / 老连接不主动删，删除一律先问。

### 币安侧删 key（已获授权时怎么点）

- 点卡片「删除」**不出弹窗**，而是该行原地弹 popover：`您确定要删除API密钥<名字>吗？` + 完整 key + `取消`/`确认`。
- 两个按钮都是 `<button>`，取 `document.querySelectorAll('button')` 里最后一个「确认」即可；**删完不再要 2FA**。
- 校验：页面上「删除」按钮个数 3 → 2，或 li 数量少一条。

## 7. 铁律

- **任何开平仓、改策略参数都要用户当轮明确同意**；“以上都要”不等于可以下真钱单。测试一律先在 `demo: true` 模拟账户跑。
- **写权限 key 与只读 key 分开**：只读常驻给 MCP 查用，写入单独一把，出事能单独吊销。
- 报告只讲结果面：`get_api_profiles` 的 `status`/余额、`get_live_strategies` 的策略数与 `totalProfitLoss`。
- key/secret 不进聊天：一次性弹窗用 `js()` 读进变量或直接写文件/gbrain。
