---
name: sp500-etf-premium-monitor
description: "Use when sp500 播报收不到/限流或要迁移重建这两个 cron。架构与 iLink 限流坑。"
version: 1.0.0
author: Hermes Agent (50.110)
license: MIT
platforms: [windows, linux]
metadata:
  hermes:
    tags: [sp500, etf, cron, weixin, ilink, rate-limit, qdii]
    related_skills: [hermes-agent, github-mirror]
---

# 标普500 ETF 溢价率监控 (sp500-etf-premium-monitor)

## 用途

每个交易日 09:35(开市)/15:05(收市) 生成三只 QDII ETF(513650 南方 / 159612 国泰 / 513500 博时)的
现价/最新单位净值/溢价率报告, 推送到用户微信; 溢价率 <3% 时弹窗强提醒。
口径: 溢价率 = (场内现价 - T-1 净值) / 净值 × 100。

## 架构(2026-09-06 修复版, 防 iLink 限流)

- **2 个 Hermes cron**: no_agent + script=`sp500_etf_premium.py` + **deliver=local**
- **微信由脚本自己发, 引擎不投递** —— 历史故障: 引擎投递(deliver=weixin)失败不重试,
  且 gateway 启动通知 + catch-up 群发补跑会在 1-2 秒内连发多条微信, 撞 iLink 限流
  → 当日 delivery_failed。
- 脚本发送策略: 全量报告固定发一条; 失败**指数退避**重试 [60s, 180s, 420s];
  10 分钟内已发过则跳过(catch-up 成对补跑只发第一条); 非交易日静默;
  设 HERMES_SP500_DRY=1 演练不发。
- state 文件(脚本同目录 sp500_etf_premium_state.json): popup_date(弹窗每日一次) +
  last_send_ts(发送去重)。
- 数据源: 腾讯 qt.gtimg.cn 现价 / eastmoney fundmobapi 净值(**需 Android UA**) /
  JJGG 申购公告。curl 直连带 2 次重试。行情时间戳非今天 → 非交易日静默。

## 关键坑(全踩过, 2026-09-06)

1. **iLink 风控 = 冷却死循环**: 每次发送收到 rate limited 都会重置 Hermes 的 30s 冷却,
   固定间隔重试永远等不到头 → **必须指数退避**(60s 起步, 总窗口 ~11 分钟)。
2. **`hermes send` 失败是静默的**: 非 --json 模式失败时退出码 1 且 stdout/stderr 全空,
   错误只在 `--json` 输出里 → 脚本必须用 `--json` 并解析 `error` 字段, 否则诊断抓瞎。
3. **台式机非全天开机**: 09:35/15:05 常错过 → gateway 登录后 catch-up 补跑 → 群发连发限流。
   根治 = 调度 + 微信通道都放 7×24 常驻机器(如 NAS 上的 Hermes VM)。
4. 弹窗(popup)仅 Windows PowerShell; 非 Windows 自动跳过, 强提醒以微信为准。
5. 文件行尾是 CRLF(patch 工具会提示转义漂移, 用行级 python 脚本替换含 \n 的块)。

## cron 参数(Hermes cronjob 工具)

| name | schedule | script | no_agent | deliver |
|---|---|---|---|---|
| sp500-etf-premium-open | `35 9 * * 1-5` | sp500_etf_premium.py | true | local |
| sp500-etf-premium-close | `5 15 * * 1-5` | sp500_etf_premium.py | true | local |

## 脚本与文件

- 本 skill `scripts/sp500_etf_premium.py` = 跨平台版(Windows/Linux 通用)
- 线上部署版: Hermes scripts 目录下的 sp500_etf_premium.py(同目录含 .log 日志与 state)
- 迁移执行清单(含具体主机上下文): `references/migrate-to-50161.md`

## 状态(2026-09-06 迁移完成)

- **50.110 两个 cron 已 pause**(open=e0291467075c / close=a2cef70a6102, 不删, 可 resume 回滚)
- **50.161 已接管**: cron c9d36d08a9c8(open) / 1f4b6f12da58(close), no_agent + deliver=local,
  脚本部署于 profile scripts 目录(~/.hermes/profiles/webui-hermes/scripts/), **发送目标=telegram
  (用户指示, 不走微信)**——send_weixin 在 50.161 改名为 send_message(target=...), 退避与去重保留
- 50.161 上其它 cron 若仍 deliver=weixin 会撞 iLink 限流(与 sp500 无关)

## 迁移到别的主机时(部署要点)

- 发送目标可换: `hermes send -t telegram` 或 `-t weixin`, 由目标机通道决定
- cron script 相对路径解析到 **profile scripts 目录**(如 ~/.hermes/profiles/<name>/scripts/),
  不是 ~/.hermes/scripts/——先确认 HERMES_HOME/profile 再放脚本
- 50.161 老坑: cronjob 工具报 "gateway not running" 可能是误报——它探测的端口被
  dashboard 占用, 用 `systemctl status hermes-gateway` / `hermes gateway status` 复核
