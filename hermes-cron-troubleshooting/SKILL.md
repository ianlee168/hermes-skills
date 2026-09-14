---
name: hermes-cron-troubleshooting
description: "Use when Hermes cron 没跑/投递失败/不准时。诊断命令、补跑机制、可靠投递架构。"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [hermes, cron, scheduler, delivery, weixin, ilink, gateway, catch-up]
    related_skills: [hermes-agent, sp500-etf-premium-monitor]
---

# Hermes Cron 诊断与可靠投递

## 回答"cron 都执行了吗"(先查证再答, 别凭列表猜)

1. `cronjob_manage list` → 逐任务看 `last_run_at` / `last_status` / `last_delivery_error` / `state`。
   状态四种: `ok`、`delivery_failed`、`error`、null(从没跑过)。一次性任务未到期时 last_run_at 为 null 是正常。
2. **区分"没跑"和"跑了但投递失败"**: `delivery_failed` 且 `last_fire_error` 为 null → no_agent 脚本执行成功,
   失败在引擎把 stdout 投到渠道(微信等)那一步, 且引擎**不重试**。脚本侧通常有本地日志, 报告内容没丢。
3. **完整执行史查 executions.db**(`%HERMES_HOME%/cron/executions.db`, sqlite, 表 executions:
   claimed_at/started_at/finished_at/status/error): `claimed_at` 远晚于计划时刻 = 补跑(catch-up)。
4. `cron/catch_up_occurrences` 计数持续涨 + `gateway-starts.log`(epoch 秒, `date -d @<ts>` 换算)
   启动时刻每天集中在固定时段 → 机器/gateway 非全天在线, 任务靠开机后成批补跑。这是"不准时"的根因。

## 跨主机 / 跨 profile 的作业: 先定位归属, 再用 CLI 在远端建

**症状**: 聊天里弹出 `Cronjob Response: <name> (job_id: <id>)`, 但本机 `cronjob_manage list`、
`%HERMES_HOME%/cron/jobs.json` 里**都没有这个 id**(`cron/output/` 下只剩已删作业的目录名)。

**原因**: 作业在**另一台机器的另一个 profile** 里, 只有那台的 gateway 在 fire。本机收到通知 ≠
作业属于本机 —— 别在本机继续翻, 也别照着通知重建一个重复的。

定位流程:
1. 本机 `grep -rl "<job_id>" %HERMES_HOME%` 找一遍, 找不到就停手。
2. 到已知常驻的机器(如 NAS 上的 Hermes VM)上 `grep -rl "<job_id>" ~/.hermes/profiles/*/cron/jobs.json`;
   命中哪个 profile, 作业就归那个 profile。
3. 读它的 `origin`(platform/chat_id)、`script`、`no_agent`、`deliver` —— 新作业沿用同一通道
   (平台分工: 本机走微信, NAS 走 telegram)。

在远端 profile 上建/改作业(非交互, 不用 agent 工具):

```bash
export PATH=$HOME/.local/bin:$PATH
export HERMES_HOME=$HOME/.hermes/profiles/<profile>   # ← 关键: 必须与 gateway 的取值一致
hermes cron create '5 8 * * *' --name <name> --script <script.sh> --no-agent \
  --deliver telegram:<chat_id>
hermes cron list --all | grep -A6 <name>      # 核对 schedule/script/deliver/next_run_at
```

- `--script` 取的是**相对 `$HERMES_HOME/scripts/` 的文件名**, 不是绝对路径; 脚本必须放在那里。
- `HERMES_HOME` 从 `/proc/<gateway_pid>/environ` 读 —— ssh 进来的 shell 里没有这个变量,
  不显式 export 就会把作业写进**默认 profile 的 jobs.json**, 它永远不会 fire。
- **必须验证 gateway 接管了**: 建完再 `hermes cron status`, active job 数要 +1(或 `hermes cron doctor`
  无新增告警)。jobs.json 写进去了 ≠ ticker 重载了。

## no_agent 脚本作业的"静默/告警"契约(建作业时一并设计)

- `--no-agent` 且 **stdout 为空 = 不投递**; 有输出才推。所以脚本要显式区分三种结果:
  健康 → 什么都不输出; 发现问题 → 输出报告; **脚本自身失败 → 输出错误并 `exit 1`**。
  最后一档不能省: 假静默会让"监控没在跑"看起来像"一切正常"。
- 幂等作业(建索引/建表/补数据)**第一步先做只读自检**, 已就绪就 `exit 0` 静默 —— 既避免天天刷屏,
  又让作业每天跑来自愈。自检要选**不触发同类限制**的手段(如 `EXPLAIN QUERY PLAN` 对 D1 是 0 行读取)。
- 首次生效要人看到: 让它**只在"这次真的改了东西"时说话**, 而不是每天报一次"正常"。

## 把新密钥送到远端主机(不回显)

远端脚本要用某个 token 时, 不要手打、不要贴进对话:

```bash
python3 -c "<本机凭证源提取 token>" | ssh <host> \
  'read -r T; T=$(printf %s "$T" | tr -d "\r\n"); grep -q "^VAR=" ~/.hermes/.env || \
   { printf "VAR=%s\n" "$T" >> ~/.hermes/.env; chmod 600 ~/.hermes/.env; }'
```

- 远端脚本自己加载: `set -a; . "${HERMES_ENV_FILE:-$HOME/.hermes/.env}"; set +a`。
  ⚠️ gateway 进程里**通常没有 `HERMES_ENV_FILE`**, 而 profile 目录下另有一份 `.env` —— 先确认该读哪份
  (`/proc/<pid>/environ`), 写错文件脚本就会报"缺少 token"。
- 送完立刻用脚本自己的只读路径验一遍(不要靠"文件里 grep 到了"当成功)。
- "凭证落在哪台机器哪个文件"顺手写进项目的 RULES/README, 下一个 agent 不必再找一遍。

## 长任务 cron 的"隐性耗时"要实测, 别靠猜

任务报"跑了 30-55 分钟"时, 先分辨是**真在传数据**还是**卡在无意义等待**: `Get-CimInstance Win32_Process`
 看还有哪些子进程活着(du / rclone / find), 看 agent.log 里该 cron session 最后一条工具调用距今多久。

两个已踩过的典型:
- **命名管道(FIFO)**: rclone 读 FIFO 无 EOF, 永久挂起且不报错, `--ignore-errors` 无效 → 源端加
 `--exclude "**/*_fifo"`。
- **慢盘上的 `du -sh`**: 数十万文件的备份盘上单跑 `du -sh <目录>` 约 7.5 分钟(180G), 若同时有其它 du/rclone
  争 I/O 可超 44 分钟不返回 → 改用 `rclone size` 或直接用 rclone 自带的 Transferred/Checks/Errors 统计核账。

另: 前台命令超时(报 timeout)后子进程**不一定会死**, 会变孤儿继续跑并占 I/O —— 收尾前查残留进程并 Stop-Process 清理。

## 长任务 cron 被"重启 drain"腰斩(桌面 App 更新是常见触发)

症状: 长任务(小时级 rclone/下载)的 run 变成 `status=unknown` / "Gateway shutdown (post-interrupt) killed
 the job's tool subprocess", 而脚本本身没报错。

根因链: 桌面 App 自动更新(或任何 planned gateway stop)会要求重启 gateway → gateway 先 defer
 stop() 等 in-flight 工作, 但**实际 drain 预算 = agent.restart_drain_timeout**(默认 0, 本机配 180s),
 远小于任务时长 → 180s 后 force-interrupt, 杀掉 cron 的 tool 子进程。

诊断: `grep -aE 'drain timed out|marked .* cron job|killed .* tool subprocess' gateway.log`,
 配合 `logs/desktop.log` 里的 `[updates] restart: Updating Hermes` 对齐时间。

修复: `hermes config set agent.cron_drain_timeout 3600`(cron 专用下限, 只会抬高 drain 预算,
 不影响聊天轮的 restart_drain_timeout)。**该值只在 gateway 启动时读一次** → 改完必须
 `hermes gateway restart` 才生效。验证: 用 venv python 调 `hermes_cli.gateway._get_cron_drain_timeout()`。

兜底: 日志导出"下一次重启会把已写完的任务当 running 卡住"的风险, 所以值不要设得比任务最坏时长还大太多。

## 改全局模型后必须复查 cron 的模型钉名(fail closed)

`hermes config set model.default <新模型>` 紧跟着会警告: **启用中、且没显式钉 provider/model 的 cron 任务**存有旧
`model_snapshot`, 下次运行会 **fail closed(直接失败)而不是静默改用新模型**。所以换完模型立刻:

1. 读 `%HERMES_HOME%/cron/jobs.json` 的 `model` / `provider` / `model_snapshot` 字段(`hermes cron list` 默认不显示这几列,
   容易漏看);只看 `enabled` 的任务。
2. 对"行为要保持不变"的任务显式钉住: `hermes cron edit <id> --provider <p> --model <m>` ——
   钉完 `model`/`provider` 落到任务顶层、`model_snapshot` 变 `null`。
3. **no-agent(纯脚本)任务没有模型字段, 不受影响, 不必钉。**
4. **限时/预览模型名(带 `-expires-on-*`)绝不要钉给 cron** —— 到期会让任务连带失效; 要钉就钉正式名。
5. 换模型前先验模型名真实性: 请求 `/v1/models` 并**读最小请求返回的 `model` 字段**。别只看 HTTP 200 ——
   旧名/别名可能被静默路由到另一个模型(返回的 `model` 字段就是答案), 也可能过期名被静默接管。

## 一次性(one-shot)任务有 120s 宽限窗, 睡过头会被直接移除

- 一次性任务(如 `'2026-09-10T23:30:00'`)的计划时刻如果错过超过 **120 秒**(机器睡眠/调度器没跑),
  调度器醒来后**不是补跑, 而是判定"永不触发"并删除该任务**, 在 `cron/output/<job_id>/` 留一条
  "Cron job removed before firing (run time outside grace window)" 记录。
- 判断任务为何没跑: 先看 `cron/output/<job_id>/` 有没有这类 md, 再查 executions.db。
- 口诀: **重要的一次性任务别只挂一次** —— 要么多挂几个时间点(深夜+早晨)互补, 要么用 recurring
  (cron 表达式)配合幂等脚本, 让每次运行自己判断"是否还需要做"。

### 最坏的组合: "干活的"和"报警的"做成一前一后两个一次性任务

实例(2026-09-13, news-xyz 建索引没能落地): 08:05 的一次性 job 干活(deliver=local 静默),
10:00 的一次性 job 读落盘报告负责报警。结果 03:45 关机 → 10:25 开机 → 10:27:00 调度器把
**两个 job 同一秒一起删掉**(都超了 120s 宽限窗)。干活的没干, 报警的也没报 —— 静默失败,
两天后才发现, 期间白烧了 2000 万行 D1 配额。

教训(排任何关键作业前先自问):
1. **工作与告警不能共享同一个失效点**(同一台机会睡的机器 + 同一个一次性时刻)。报警必须比工作
   **更晚、更频繁、且不依赖工作的产物**(靠外部事实校验, 如用量数字/查询计划)。
2. **关键且有时效窗口的活, 只排在 7×24 常驻主机上**(NAS 上的 Hermes VM), 用 recurring 表达式;
   非 7×24 主机只适合"迟到无害"的活。recurring 漏跑会 catch-up, 一次性漏跑会被删除。
3. **`deliver=local` 的静默作业必须配一条独立的交叉验证**, 否则"没跑"和"跑了没事"在表面上一样。
4. 收尾时说"已排 job"时必须加一句**怎么验证它真跑了**(下一天的外部数字/自检输出), 否则等于许愿。

## 台式机/非 7×24 环境的 cron 规律

- Windows gateway 生命周期 = 开机+登录(schtasks ONLOGON, `hermes gateway install` 注册)或桌面 app 拉起;
  关机/桌面退出 → 调度停。计划任务 `LastTaskResult=0` 只说明登录时启动成功, 不代表全天在跑。
- **排期必须落在机器的开机窗口内**: 本机(50.110)每日 04:00 关机 → 日常任务排 02:00(`0 2 * * *`), 留出余量;
  实测 09-13 03:45 关机 / 10:25 开机 —— **早上 08:00-10:30 常常是关机窗口**, 别把 08:05 这类时刻排在台式机上。
  排在关机点的任务等于永远赶不上, 只会被记成漏跑、靠开机 catch-up 补跑 —— 而补跑时段恰好撞上白天桌面更新(见上节)。
  排任何周期任务前先确认"这台机器什么时候开机、什么时候关机"。
- 启动瞬间会做两件事: 往 home channel(微信)发启动通知 + 成批补跑积压任务 → 1-2 秒内多条微信连发
  → 撞 iLink 限流 → 引擎投递失败且不重试, 当日播报全丢。
- 检查: `hermes gateway status`(schtasks + Startup + PID 合并视图)。
- 根治: 调度 + 消息通道都迁到 7×24 常驻机器(NAS 上的 Hermes VM); 迁移完成前用脚本自管架构兜底。

## 可靠投递架构: deliver=local + 脚本自管发送

对"必须送到"的例行播报 cron, 别依赖引擎投递:

- cron 设 `deliver=local`(stdout 只存档), 渠道发送由脚本负责 —— 脚本能重试、能去重、节奏可控。
- 脚本内发送统一 `hermes send -t weixin --json <text>`; 成功 = exit 0 且 JSON 无 `error` 字段。
- 失败按**指数退避**重试(60s/180s/420s, 约 11 分钟窗口)。固定间隔必死循环:
  iLink 每次返回 rate limited 都重置 Hermes 的 30s 冷却, 固定 45s 重试永远等不到头。
- open+close 成对补跑时用 state 文件记 `last_send_ts`, 10 分钟内去重只发第一条。
- 无内容/非交易日静默退出(no_agent 空 stdout 不投递)。
- 完整实例与迁移执行清单: skill `sp500-etf-premium-monitor`。

## 微信 iLink 专属坑

- `hermes send` **非 --json 模式失败时退出码 1 且 stdout/stderr 全空**(错误只在 --json 里)
  → 任何包了 hermes send 的脚本必须用 --json 并解析 error, 否则诊断抓瞎。
- iLink 风控是通道级的, 窗口可达小时级; 风控期间连发必 ret=-2。
  同一微信号两个 gateway 长连接会互踢(迁移通道前先确认)。
- 手动验证通道: `hermes send --list`(看可用目标)、`hermes send -t weixin --json "test"`。
