---
name: spot-trade-execution
description: Use when placing real spot trades under hard risk caps.
version: 1.0.0
author: 110妹
license: MIT
platforms: [windows, linux, macos]
tags: [binance, spot, risk-management, oco, trading]
metadata:
  hermes:
    tags: [binance, spot, risk-management, oco, trading]
    triggers: ["实盘", "下单", "开仓", "单笔风险", "最大回撤", "止损", "止盈", "OCO", "模拟盘转实盘", "本金上限"]
---

# 小额实盘下单（硬风控）

## When to Use

- 用户授权用真钱跑策略（“实操吧”“同意，就这么干”），需要把仓位额度、止损止盈、熔断真正落实。
- 要在交易所 REST API 上直接下单，而不是通过机器人平台（平台的 Open API 可能只放模拟盘，见 `3commas-mcp`）。
- 用户在问“能不能日赚 X% / 几天翻倍”这类收益目标，需要先把数学说清再谈执行。

## 硬规矩（不跟模型自觉走，跟代码走）

- **风控参数写在执行器代码里**：超单笔上限、超并行笔数、当日亏损触熔断、余额不足 —— 四种情况直接 `refused` 返回，不靠“我记得要小心”。
- **必须先把三个数字拿到手才下单**：本金上限、单笔上限、最大回撤/熔断线。用户说“你定个最稳妥的”——就按下节默认档给，并当场把数值念给用户确认（他同意的是数值，不是“小心点”）。
- **只做 1x 现货**，不碰合约/杠杆，除非用户单独明确授权杠杆倍数。
- **止损用交易所侧挂单（OCO），不是靠盯盘**：市价进场后立刻挂 OCO（止盈 limit + 止损 stop-limit），进程被杀也有保护。
- **判断成交只认回读**：`/api/v3/order` 返 200 只是接单；必须回读 `fills` 算真实均价、`openOrders` 确认 OCO 两腿都在，再报给用户。
- **不承诺收益率**。用户提“日 X% / N 天翻倍”就给复利数学与概率（日 10% × 6 天 ≈ +77%；6 天翻倍需 12.25%/日；日 10% 年化 ≈1e15 倍；6 次方向全对概率 1.56%），然后明说做不到，把话题转成风控参数。
- **报告只讲结果面**：成交均价、数量、手续费、当前浮盈亏、止损止盈价、剩余额度。不写过程叙事。

## 默认风控档（用户要求“你按最稳妥设”时用这组）

| 项 | 值 | 理由 |
|---|---|---|
| 本金上限 | 账户全部可动用（用户已明确放开时） | 用户拍板，不是我们拍板 |
| 单笔风险 | 总资产 1% | 连亏 10 笔才 -10% |
| 单笔成本上限 | 由“单笔风险 ÷ 止损比例”反算（1% 风险 / 3% 止损 ≈ 总资产 1/3） | 保证止损触发时亏得起 |
| 并行笔数 | ≤2 | 相关性风险与手动干预上限 |
| 止盈 / 止损 | +6% / -3%（2:1） | 胜率 40% 即正期望 |
| 熔断 | 当日已实现净亏 ≥ 固定小数额（如 5 USD）立即停手 | 防情绪加仓 |

参数落 gbrain（如 `trading/risk-limits-<期>`），后续会话按同一页执行，不凭记忆。

## 流程

1. **授权与参数**：拿到本金/单笔/回撤三件，写进 gbrain；缺一件就只跑模拟盘。
2. **准备一把会下单的交易所 key**：权限 = 允许读取 + 允许现货交易（**禁提现、禁合约**，除非另行授权）；IP 限制选“只访问受信任的 IP”并填**本机出口 IP**（`curl https://api.ipify.org`），否则本机调用全部 `-2015`。建 key 的强验证坑见 `exchange-api-connectivity`。
3. **先验签名链路**：跑 `balance` 子命令，能拿到 free 余额才说明 key/时间戳/签名都对；报 `-2015` 查 IP 与权限，报 `-1021` 查本机时钟。
4. **首单用最小额**：先下一笔接近最小成交额的单，回读 `fills` 与 `openOrders`，确认签名、成交、OCO 三件事都对，再加到正常仓位。
5. **进场即挂 OCO**（见下节），把成交均价、TP/SL 价、最大亏损额算给用户看。
6. **对账**：每天读 `openOrders` + 当日 `myTrades` 算已实现盈亏，触熔断就停手报告。

## Binance 现货下单要点

- 签名：`HMAC-SHA256(secret, queryString)`，参数含 `timestamp` 与 `recvWindow`；头 `X-MBX-APIKEY`。
- 市价买入按金额：`type=MARKET&quoteOrderQty=<USDT>`（按数量则用 `quantity`）。
- **现货的双向保护只能用 OCO**：`POST /api/v3/order/oco`，参数 `price`（止盈）、`stopPrice`（止损触发）、`stopLimitPrice`（止损限价，比 stopPrice 再低 0.5% 保证成交）、`stopLimitTimeInForce=GTC`。单独挂 `STOP_LOSS_LIMIT` 只保护下侧。
- 撤单：`DELETE /api/v3/order` 用 `orderId` 或 `origClientOrderId`；**OCO 要用 `DELETE /api/v3/orderList` 带 `orderListId`**，按单腿 `orderId` 会报 order does not exist。
- **XRP 有储备**：币安 XRP 余额里约 10 XRP 是储备（reserve），卖全额会报 `-2010 insufficient balance`，要按 `free - 10` 下，剩下的卖掉不动。
- **低于最小成交额卖不掉**：USDC 3 USD 这类零头会因 `minNotional` 5 USD 直接报废，别反复重试；无现货交易对的（SOLO、ETHW）也只能留着。
- 现成执行器：`D:\hermes-test\binance_trade.py`（= 本 skill 的 `scripts/binance_spot_executor.py`；caps 内置，`buy/open/balance/price/cancel` 子命令；凭据 `D:\hermes-test\.bnb_key.json`，用完撤）。

## 告警与日报架构（50.110 下单 / 50.161 24/7 推送）

- **下单与对账只能在 50.110**：API key 的 IP 白名单绑死本机出口 IP，161 查不到账户。
- **告警跑在 50.161**（24/7，只看公开行情，不需要 key）：`~/trading/vmon.py` + crontab `*/5`；持仓表靠 50.110 的 `positions.json` scp 过去（执行器下单后自动同步，日报也会同步一次）。
- 告警档位：仓位偏离 3/4.5/6%（用户 2026-11-08 定的起报线 3%，之前 1.5% 太吵）、距止损/止盈 <1%、15 分钟 ≥3% 急拉急杀、合计浮亏 ≥5 USD；`alert_state.json` 做档位去重（同档 30 分钟冷却、回落 6 小时才重报）。
- Telegram 推送：50.161 的 `~/.hermes/.env` 里有 `TELEGRAM_BOT_TOKEN`（bot `yongggbot`），chat_id 在 `~/.hermes/.channel_directory_*.tmp`。50.110 没有 telegram token，要推就从 110 `ssh 161 "python3 vmon.py --send-text '<text>'"`。
- 每日简报 cron 在 50.110（01:00，`daily_pnl_report.py`），因为要读私有账户；脚本自己 ssh 到 161 推 Telegram，同时在 chat 里留一份。
- **简报脚本必须对每个数据源单独降级，一个接口抖动不能整份不报**（2026-11-13 01:00 真实事故）：
  `openOrders` 单次抖动返回 `{"error":{...},"status":500}`，调用方直接 `for o in legs: o["symbol"]`
  → 遍历字典拿到的是键名字符串 → `TypeError: string indices must be integers` → 整轮 exit 1，
  当天简报直接消失（cron 只记 `last_status=error`，用户什么都收不到）。
  修法：`api()` 只读调用 4 次退避重试 + 每个取数点在拿到非预期类型时打 warn 并降级
  （openOrders 当无挂单、account 当「取不到资产」、报价失败不再按 0 静默计入）。
- **漏掉的某天可回补**：`python daily_pnl_report.py --date 2026-11-12 --no-telegram`
  （`--date` 只算那天窗口、**不写 pnl_snapshot.json**，否则「较上次快照」的基线会被历史日期污染）。
- **投递时间会飘，不是故障**：01:00 时机器常处于关机（11-09 21:45 关 → 11-10 19:00 开、11-11 16:26 才开），
  Hermes cron 在开机后补跑，于是简报 19:01 / 16:26 才到，标题仍是正确的「前一天全天」（窗口按日期算，不按运行时刻算）。
- 机器可用时段：50.110 只排 15:00-01:00 的 cron，01:42-08:55 关机 —— 夜间监控必须放 161。

## 坑

- **已实现 PnL 必须按比例计入**：卖出量往往大于本轮买入量（例如老仓 2000 DOGE 里只带 154 的新仓），如果把整笔 `quoteQty` 都减成本，会凭空多出一大笔“利润”（实测虚报 +132 USDT，而真值是 +0.07）。正确：`pnl += quoteQty * (take/qty) - avg*take`。这个数值直接喂给熔断判定，算大了就不会止损停手。

- **手续费从 base 币扣 → OCO 报 -2010**：市价买入后 `executedQty` 可能**大于**该币的 `free`（差在手费），直接拿 `executedQty` 挂 OCO 会 `-2010 inufficient balance`，仓位在这段时间是裸露的。正确写法：`qty = min(executedQty, 该币 free)`，再按 `stepSize` 用 **ROUND_DOWN** 取整（默认 `quantize` 是 half-even，会向上舍入）。剩下的零头（如 BTC 0.00000882）小于一步，只能 unprotected 留着。

- **假熔断**：用 `myTrades` 算当日已实现 PnL 时，如果把 `isBuyer=true` 的成交当成亏损（`-quoteQty`），每一笔买入都会把熔断直接点燃（实测：买入 10.9 USD 就报“当日亏损触及 5 USD”）。必须用**均价法**：维护 qty/cost，只在卖出且 qty>0 时结算 `quote - avg*qty`；今日之前的成交只用于恢复持仓与成本。
- **挂单会锁仓**：`/api/v3/account` 的 `free` 不含 OCO 挂着的币（`locked` 里），总资产估值要用 `free + locked`，否则会少算一整个仓位的价值（实测少报 $60）。

- **OCO 必须先按 PRICE_FILTER / LOT_SIZE 取整**，否则 `-1013 Filter failure: PRICE_FILTER`。取 `GET /api/v3/exchangeInfo?symbol=X` 的 `PRICE_FILTER.tickSize` 与 `LOT_SIZE.stepSize`，用 `Decimal` 向下取整后再 `format(x,'f')` 发（DOGEUSDT tick=0.00001、step=1）。**进阶后用 `FILLED`、但 OCO 报错时仓位是裸露的**，发现失败要在同一分钟内用正确精度补挂，并在报告里写明裸露时长。
- **钱包分层不是漏报**：币安 `资金账户(Funding)` 与 `现货(Spot)` 分开——`/api/v3/account` 只返回现货；资金账户走 `POST /sapi/v1/asset/get-funding-asset`。拿到的总数对不上用户看到的总资产时，先查资金账户再下“平台漏报”结论。
- **划转要单独权限**：key 没有“允许划转”时 `POST /sapi/v1/asset/transfer` 报 `-1002 You are not authorized`。资金账户里的币不能自己搬到现货，需用户在 App 划转或另授权限（默认不给）。

- 最小成交额截断：金额大于最小额的订单可能只成很小一笔（例如 100 USDT 在 BTCUSDT 只成 0.001 BTC），收益与风控都按**实际** `totalEntryCost`/`cummulativeQuoteQty` 算，别按下单金额算。
- **平台侧余额与交易所不一致时以交易所为准**：机器人平台（3commas 等）的余额是快照，会漏币/滞后；下单前用交易所 `account` 或交易对页的“可用/可卖”核。
- **余额在其它币里不等于能下单**：现货交易要 quote 币（USDT）。持仓变现是**用户决策**——要卖 DOGE/ETH 换 USDT 先问一句，别自己动手。
- **API key 没有交易权限时**下单报权限错，不是参数错；先去交易所核对权限位。
- 别把“挂单已创建”当“已平仓”：止盈止损挂着时仓位仍在场，浮盈亏要按现价算。
