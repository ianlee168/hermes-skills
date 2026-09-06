# sp500 播报 cron 迁移到 50.161(Hermes VM)执行清单

> 生成方: 50.110 Windows Hermes(2026-09-06)。用户转发给 50.161 的 Hermes 会话执行。
> 背景: 50.110 是台式机, 非全天开机, 09:35/15:05 cron 常年错过靠补跑, 且微信 iLink
> 通道挂在台式机上, 每次开机群发补跑撞限流(delivery_failed)。50.161 跑在 Unraid NAS
> 上(VM autostart, 7x24), 迁过去后任务准点、通道常驻、限流消失。

## 0. 本机环境自查(每条都要实际跑, 别猜)

```bash
hermes --version                 # 需 ≥ 0.21(与 50.110 同代, 有 cron no_agent + deliver=local)
hermes gateway status            # gateway 是否常驻 running
which hermes                     # 脚本 subprocess 调用需要 CLI 在 PATH
ls ~/.hermes/scripts/ 2>/dev/null || ls "$HERMES_HOME/scripts/"   # Hermes scripts 目录
```
- cron 创建用 Hermes 的 cronjob 工具(action=create), 参数见第 3 步。
- 脚本发送微信用 `hermes send -t weixin`, 所以 **必须确认 weixin/iLink 通道**:
  ```bash
  hermes gateway status          # platforms 里 weixin 是否 connected
  ```
  ⚠️ 若 50.161 与 50.110 配的是**同一个 iLink 微信号**, 双端会互踢: 50.161 上线前/后
  必须停用 50.110 的 weixin 平台(由 50.110 侧执行, 用户协调)。若 50.161 还没有 weixin
  通道, 先配好并确认 `hermes send -t weixin -q "test"` 用户微信能收到, 再做下面步骤。

## 1. 放脚本

把本目录的 `sp500_etf_premium.py`(跨平台版: Ubuntu 自动跳过 Windows 弹窗)
放到 Hermes scripts 目录(即第 0 步查到的路径, 通常 `~/.hermes/scripts/`)。

## 2. 单测(不发微信)

```bash
cd ~/.hermes/scripts
HERMES_SP500_DRY=1 python3 sp500_etf_premium.py --force
# 期望: 输出三只 ETF 报告 + 末尾 "[dry-run] ... 跳过微信发送"
```
(依赖: python3 + curl; 拉取腾讯行情 qt.gtimg.cn + eastmoney fundmobapi, 均走公网。
行情时间戳非今天时脚本静默退出, 所以测试必须带 `--force`。)

## 3. 创建 2 个 cron(用 cronjob 工具, no_agent + deliver=local)

架构与 50.110 修复版一致: **引擎不投递, 微信由脚本自己发**(脚本内置 45s x 5 次重试 +
10 分钟去重, 解决限流与 catch-up 成对补跑双发)。脚本会自己写本地日志与 state 文件
(在脚本同目录)。

| 字段 | 开盘任务 | 收盘任务 |
|---|---|---|
| action | create | create |
| name | sp500-etf-premium-open | sp500-etf-premium-close |
| schedule | `35 9 * * 1-5` | `5 15 * * 1-5` |
| script | sp500_etf_premium.py | sp500_etf_premium.py |
| no_agent | true | true |
| deliver | local | local |
| prompt | (任意简短说明, no_agent 下被忽略) | 同左 |

## 4. 真实发送验证(会发一条微信给用户)

```bash
cd ~/.hermes/scripts && python3 sp500_etf_premium.py --force
```
- 期望: 用户微信收到一条完整播报(标题 "标普500ETF溢价率监控 · MM/DD HH:MM 开市")。
- 若失败: 脚本会重试约 5 分钟并打印 `[warn] 微信发送失败...`——把 warn 内容回报,
  多半是 iLink 通道/互踢问题。
- 验证 state: 发送成功后同目录 `sp500_etf_premium_state.json` 会出现 `last_send_ts`。

## 5. 收尾(全部通过后)

1. 50.161 两个 cron 各自手动 `run` 一次或等下一交易日 09:35 实战。
2. **通知用户让 50.110 停用旧的 sp500-etf-premium-open/close 两个 cron**(防双发;
   50.110 侧动作, 由用户转达后 50.110 执行 pause, 不删除)。
3. 建议把本脚本同步进 ianlee168/hermes-skills 仓库或 gbrain, 防丢失。

## 6. 回滚

若 50.161 侧有问题: 直接 pause/remove 新 cron, 通知用户恢复 50.110 旧 cron(resume)。
50.110 旧 cron 在迁移完成前**保持 enabled 不动**(唯一入口是用户通知后再停)。

## 已知取舍

- Windows 弹窗强提醒在 Ubuntu 上无(脚本已跳过); <3% 强提醒以微信消息为准。
- 溢价率阈值/口径与 50.110 版完全一致(腾讯现价 + eastmoney 净值, 每日净值 T-1)。
- 本文件是执行指令, 每步都要实测回报, 不要跳过自查直接建任务。
