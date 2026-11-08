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
    triggers: ["3commas MCP", "3commas API", "3commas 工具", "开仓", "平仓", "策略", "机器人", "get_live_strategies", "place_strategy_trade", "订阅套餐", "日收益目标", "几天翻倍", "模拟盘", "现货余额"]
---

# 3commas MCP / REST API

## When to Use

- 要让 agent 直接看/管 3commas 账户（连接、余额、策略、历史），而不是点网页。
- 用户问“3commas 有没有 skill / 能不能你自己操作账户 / 帮我开个仓”。
- 要评估 3commas 套餐能不能跑实盘。
- 网页端 API 页创建 MCP key、或 MCP 连接报错时排障。

配对 skill：`exchange-api-connectivity`（交易所 API key 建/删、IP 白名单、强验证）；`spot-trade-execution`（实盘下单与硬风控）。

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
- 日报脚本：`~/AppData/Local/hermes/scripts/3commas_trial_report.py`（cron 每天 21:00）——输出 demo 策略盈亏 + 现货余额日变化（自带 `D:\hermes-test\3c_balance_snapshot.json` 快照比对），自己按 `get_exchange_markets` 现价折出 `total_usd`。cron 用 `script=` 把这个 JSON 注入 prompt，agent 只负责措辞，不在回复里重算数字。
- `mcp3c_call.py` 默认把 stdout 全额打印；不要加 `[:4000]` 截断，否则 JSON 不完整直接解析失败。

## 4. 工具清单（17）

只读：`get_supported_exchanges`、`get_exchange_markets`（参数是 `{"exchanges":["BINANCE_FUTURES"]}`，**不是** `exchangeCode`）、`get_exchange_families`、`get_api_profiles`、`get_strategy`、`get_live_strategies`、`export_strategies_history`、`export_strategy_orders_history`

写/交易：`create_api_profile`、`edit_api_profile`、`delete_api_profile`、`place_strategy_trade`、`edit_trade_strategy`、`cancel_strategy`、`close_strategy_market`、`place_strategy_market_enter`、`place_strategy_swing`

`get_api_profiles` 每个市场一条：`exchange.code` ∈ `BINANCE`(现货) / `BINANCE_FUTURES`(USDT-M) / `BINANCE_DELIVERY`(COIN-M)，同一连接共享 `masterCode`，`status` 可能是 `active` / `no_assets`，`demo: true` 是模拟盘；现货 `balance.assets.<币>.total` 是数量。

策略对象字段（`get_strategy` / `get_live_strategies`）：`pair` 是**纯字符串**（`"BTCUSDT"`，不是对象）、`pairSymbols: {base, quote}`、`profitLossInPercent` 直接给百分比、`takeProfits[0].price/status`、`stopLossStatus`（`not triggered`）、`totalEntryCost`/`totalEntryAmount`/`totalProfitLoss`、`paperTrading`、`status` ∈ `new`/`entered`/…。

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

**Open API / MCP 在免费与试用套餐下只放 DEMO 交易。** 对 `demo: false` 的 profile 调 `place_strategy_trade` 会被服务端直接拒，报错原文：`Only DEMO trading allowed. Please upgrade your plan to be able to trade with Exchange API profiles.` 所以“试用期用 MCP 跑真钱”这条路不存在 —— 要么付费订阅，要么绕开 3commas 直接调交易所 REST API（见 `spot-trade-execution`），3commas 留着跑 demo 做对照。另外 **Free 套餐在网页端也不能交易**（手动也不行），只能连交易所看余额；试用到期降 Free，真钱单要用户当轮点头。

## 6. 安全盘点必查项

- `设置 → 安全`：`2FA 身份验证状态：已禁用` 是常见默认状态，**开实盘前必须打开**（需用户用验证器 App 扫码）。开启后该行变「已启用」+「禁用」按钮；已有 API key / MCP 不受影响。
- 交易权限的 key 必须配 IP 白名单；交易所侧白名单缺 IP 会导致全部市场认证失败（见 `exchange-api-connectivity`）。
- 老 key / 老连接不主动删，删除一律先问。

### 币安侧删 key

流程与选择器见 `exchange-api-connectivity` §2「删 key」——popover 原地确认，删完不再要 2FA，校验看列表少一条。

## 7. 余额口径：3commas 视图 ≠ 真实余额

- `get_api_profiles` 的现货 `balance.assets` 是 3commas 侧快照，**会漏币、会滞后**：实测币安现货真实 ≈471 USD，3commas 只报 249.7 USD，缺 1000 DOGE 和全部 ETH；币安交易页确认这两项都是「可用」，不是挂单冻结。差额不是亏损、不是资产消失，别当异常报警。
- 报数前先核对真实余额：`https://www.binance.com/zh-CN/trade/<BASE>_USDT?type=spot` 页里的「可用 / 可卖」就是该币真实可用量（`/my/open-orders`、`/my/orders` 这类 /my/ 页可能整页报「系统遇到问题」，交易对页更稳）。
- 口径固定成两行：「3commas 视图」+「币安真实」，差额写明原因（快照滞后）；仓位与风控一律按币安真实值算。
- 日变化只能自建快照比对（`3c_balance_snapshot.json`）——3commas 不提供历史余额接口，没快照就别编“较昨日 +X”。

## 8. 铁律

- **任何开平仓、改策略参数都要用户当轮明确同意**；“以上都要”不等于可以下真钱单。测试一律先在 `demo: true` 模拟账户跑。
- **写权限 key 与只读 key 分开**：只读常驻给 MCP 查用，写入单独一把，出事能单独吊销。
- 报告只讲结果面：`get_api_profiles` 的 `status`/余额、`get_live_strategies` 的策略数与 `totalProfitLoss`。
- **不承诺收益率**：用户提“日 X%、N 天翻倍”这类目标时，先给复利数学（日 10% × 6 天 = +77%；6 天翻倍需 12.25%/日；日 10% 年化 ≈1.3e15 倍），再明说做不到、不当业绩承诺；把话题转成风控参数（单笔风险 ≤1–2%、杠杆 ≤2x、硬止损、并行笔数），并把「不亏 + 测清滑点和手续费」定成试用期的硬指标。
- **真钱下单前必须拿到三样**：本金上限、单笔上限、最大回撤。缺一样就只跑 `demo: true`，不要用“先小仓试试”替代授权。
- key/secret 不进聊天：一次性弹窗用 `js()` 读进变量或直接写文件/gbrain。
