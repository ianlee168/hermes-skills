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

### 跨机迁移一个已有作业(换机器)的收尾顺序

1. **先在目标机建好 + 真验证**,源机一切不动:目标机跑一次真实发送(`--force` 或手动 run),
   确认用户**真收到**(别只看日志写了"已发")且 executions 状态 ok。
2. 验证通过后才 **pause 源机作业(不删)** —— pause 可随时 resume,就是回滚路径;目标机跑稳了
   至少一个自然周期再考虑删除。两机同开 = 双发。
3. **时点敏感的一次性提醒(订阅取消这类)必须放在 7×24 常驻机**:台式机上错过触发窗
   (一次性任务超 120s 宽限直接删除)就是彻底漏报,不可补。非 7×24 机器只放"迟到无害"的活。
4. 迁移后立即更新对应 skill / 共享约定文档里的**归属、通道、job id** —— 否则下一个会话还会去源机找,
   甚至重建一份造成双发。
5. 通道按机器分工走,别沿用旧机通道:本机(Windows)推微信,NAS 上的 Hermes VM 推 telegram。

## no_agent 脚本作业的"静默/告警"契约(建作业时一并设计)

- `--no-agent` 且 **stdout 为空 = 不投递**; 有输出才推。所以脚本要显式区分三种结果:
  健康 → 什么都不输出; 发现问题 → 输出报告; **脚本自身失败 → 输出错误并 `exit 1`**。
  最后一档不能省: 假静默会让"监控没在跑"看起来像"一切正常"。
- 幂等作业(建索引/建表/补数据)**第一步先做只读自检**, 已就绪就 `exit 0` 静默 —— 既避免天天刷屏,
  又让作业每天跑来自愈。自检要选**不触发同类限制**的手段(如 `EXPLAIN QUERY PLAN` 对 D1 是 0 行读取)。
- 首次生效要人看到: 让它**只在"这次真的改了东西"时说话**, 而不是每天报一次"正常"。

## agent 型作业撞上 gateway 环境损坏 → 降级成 no_agent 脚本(止损)

**判据**: 作业的真实工作根本不需要模型(纯 rclone/curl/命令行), 却报
`last_error: RuntimeError: Failed to initialize OpenAI client: No module named 'pydantic_core._pydantic_core'`
或类似的 gateway 环境损坏错误 → 这不是"数据出问题", 是**执行路径**出问题。

**根因**: agent 型作业在 gateway 进程内构造模型客户端(`cron/scheduler.py::_construct_cron_agent`),
所以继承 gateway 被污染的 `sys.path`; 而 `no_agent` 在 `run_agent` 之前就短路(`cron/scheduler.py:2187`),
**结构性免疫**同一环境损坏。

**做法**:
1. 把作业 prompt 里那些"运行补丁"(命令级参数、排除项、已知挂死源、验证口径)搬进一个脚本 ——
   **prompt 不是文档, 它就是作业本体, 转换时必须逐条落地**, 否则等于静默丢掉几个月踩出来的经验。
2. 脚本放 `$HERMES_HOME/scripts/`(作业只认这个目录下的文件名, 绝对路径也会被拒)。
   `.sh/.bash` → Git Bash; 其它后缀 → `sys.executable`, 所以优先写 `.py`(不赌 bash 在 PATH 上)。
3. `hermes cron edit <id> --no-agent --script <name.py>`; prompt 字段留着当文档, 不用清。
4. 顺带收益: 不再烧 token, 输出确定性更高。

**验收必须走真 fire, 不能用 `hermes cron run` 代替**: 那个命令是 CLI 自己当 owner(`source=direct`),
走不到出问题的那条路径。正确做法是把 schedule 临时改成 **4-5 分钟后的某一分钟**, 等 ticker 自己 fire,
在 `hermes cron runs` 里确认 `source=builtin` + `status=completed`, 读 `cron/output/<job_id>/<ts>.md`,
**然后立刻改回原表达式并复核 `next_run_at`**(改完不复核 = 埋一个每 5 分钟跑一次的雷)。


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

## 验证"时钟事件"的结果: 别在会话里 sleep 等

要在某个固定时刻之后核实效果(配额 00:00 UTC 重置、每日 11:00 CST 的抓取、次日 09:00 的日报)时:

- **不要用前台 `sleep N` 等** —— 前台命令有上限(实测 420s 被杀), 会把会话拖死; 而你等的时刻往往还在
  未来, 等于白等一轮。
- 事件**已经过去** → 直接查, 而且要看**按小时分桶**的原始数字(如 `datetimeHour`); 用"整天合计"去判断
  "某个窗口变没变"会得出错误结论。
- 事件**还没到** → 先把方案与**预期**交付出去, 用一条**已存在的周期作业**当验收(次日那条日报就是判决),
  并写清"看哪一条、预期看到什么、看到什么才算没过"。
- **预期值**与**实测值**必须分开标注; 时间不够时不要拿一个看起来合理的数字填空。
- 用户拿一条旧预警来问"解决了吗" → 用**当次重新拉到的数字**回答(顺带说明那条预警报的是前一天),
  不要复述上次的结论。

## 长任务 cron 的"隐性耗时"要实测, 别靠猜

任务报"跑了 30-55 分钟"时, 先分辨是**真在传数据**还是**卡在无意义等待**: `Get-CimInstance Win32_Process`
 看还有哪些子进程活着(du / rclone / find), 看 agent.log 里该 cron session 最后一条工具调用距今多久。

两个已踩过的典型:
- **命名管道(FIFO)**: rclone 读 FIFO 无 EOF, 永久挂起且不报错, `--ignore-errors` 无效 → 源端加
 `--exclude "**/*_fifo"`。
- **慢盘上的 `du -sh`**: 数十万文件的备份盘上单跑 `du -sh <目录>` 约 7.5 分钟(180G), 若同时有其它 du/rclone
  争 I/O 可超 44 分钟不返回 → 改用 `rclone size` 或直接用 rclone 自带的 Transferred/Checks/Errors 统计核账。

另: 前台命令超时(报 timeout)后子进程**不一定会死**, 会变孤儿继续跑并占 I/O —— 收尾前查残留进程并 Stop-Process 清理。

**⛔ 别从 agent 自己的 terminal 里跑 `hermes cron run`**: 该命令让 **CLI 进程本体成为 run owner**
(`source=direct`)。工具调用一旦超时把 CLI 杀掉, 这次 run 就被记成
`unknown` / "Scheduler restarted after this execution's owner exited before a durable terminal state",
而它拉起的子进程(rclone 等)继续孤儿式跑下去。要手动触发: 用 `background=true` + `process_manage(wait)`
让 CLI 活到结束, 或者干脆按上面的"临时 schedule 真 fire"走。

**脚本里判成败别直接看 rclone 退出码**: 传输有错时 rclone 报 `Failed to copy with N errors` 并 **exit 1**,
而 appdata 这类活容器的目录里, "边传边被删/改"是常态(`failed to set directory modtime`、
`failed to open source object: Open failed: file does not exist`、qbittorrent ipc-socket)。脚本要**分类**这些
良性 churn 错误(并设一个上限, 超了才算真失败), 否则日报天天"失败", 真失败反而淹没在噪声里;
同时注意统计块里的 `Errors: 7 (retrying may help)` 是计数器不是错误事件, 别把它算进去。

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
- **排期必须落在机器的开机窗口内, 而且要说得出窗口的起止**(2026-09-20 实测校准, 别再凭旧印象):
  50.110 台式机 **关机 01:42–03:26**(`Get-WinEvent -FilterHashtable @{LogName='System';ID=1074}` 实测:
  01:42/02:00/02:54/03:04/03:06/03:25/03:26), **开机 08:55–14:02**(实测 08:55/10:33/14:02, 另有 15:03/16:34/22:09)。
  → **安全窗口 ≈ 15:00–01:00;危险窗口 ≈ 02:00–14:00**(即 08:00-14:00 的任何时刻都别排)。
  (2026-09-22 复测与上一致: 关机 02:01/02:54/02:59/04:15, 开机 10:33/10:35/11:16/14:02 → 窗口结论不变。)
  以前这条写的"每日 04:00 关机 → 日常任务排 02:00 留余量"**是错的**: 02:00 本身就在关机窗里,
  于是三个 job 长期只能靠 catch-up 补跑(实测 appdata 同步迟到 12h、gbrain 每周清理迟到 10.5h、工具升级迟到 1.5h)。
  校正后: appdata 同步 02:00→23:00、gbrain 每周清理 周日03:30→周日23:30、工具自动升级 09:00→20:00(每 3 天)。
  排在关机点的任务等于永远赶不上, 只会被记成漏跑、靠开机 catch-up 补跑 —— 而补跑时段恰好撞上白天桌面更新(见上节)。
  排任何周期任务前先确认"这台机器什么时候开机、什么时候关机"。
- 启动瞬间会做两件事: 往 home channel(微信)发启动通知 + 成批补跑积压任务 → 1-2 秒内多条微信连发
  → 撞 iLink 限流 → 引擎投递失败且不重试, 当日播报全丢。
- 一眼看长期迟到: `hermes cron list --all` 每个 job 的 `Dispatch:` 行 ——
  `⚠ late: scheduled <t>, ran <t> (Nh late)` 或 `⚠ catch-up after missed fire: scheduled …, ran … (Nh late)`
  就是"排在了关机窗里"的铁证(recurring 会补跑所以不丢, 但时间表形同虚设; 一次性任务超 120s 则直接删)。
  补跑还要注意: 补跑常发生在**开机瞬间**(与启动通知一起), 多条并发会撞 iLink 限流。
- 检查: `hermes gateway status`(schtasks + Startup + PID 合并视图)。
- 根治: 调度 + 消息通道都迁到 7×24 常驻机器(NAS 上的 Hermes VM); 迁移完成前用脚本自管架构兜底。
- **跨机分工(2026-09-22 陛定)后, 派给 50.161 的定点活要落成什么形态**: 实测那台 `hermes-gateway.service`
  是 **failed**, 没人 tick Hermes 任务队列(两处 store 心跳都停在 08:00), 当天真正在跑的是**系统 crontab 里那 8 个**
  (01:00 备份 / 03:00 脑备份 / 08:00 auto-update+HA / 09:00 immortalwrt+lucky / 16:00 frigate / 20:00 新闻)。
  → 派过去的定点活**用系统 cron 或 systemd timer 落地最稳**; 非要用 Hermes 任务库, 得先起 gateway
  (会抢 Telegram/微信 token, 需用户同意)。别默认"对面 7×24 就万事大吉"——先确认它的调度器真的在 tick。

## 排期审计: 一次性把全部作业对照开机窗口过一遍

用户抱怨"某时刻的活不该在那时跑"时, 别只修他指的那一条 —— 同一台机器上其它作业通常排得一样错:

1. 列全: `hermes cron list --all`(本机) + 远端 profile(`HERMES_HOME=~/.hermes/profiles/<p> hermes cron list --all`)。
2. 逐条读 `%HERMES_HOME%/cron/jobs.json` 拿 cron 表达式, 把**小时**跟开机窗口对照; `Dispatch:` 行带
   `⚠ late: … (Nh late)` 的作业就是已确诊的错排(迟到几小时 = 它离窗口有多远)。
3. 改: `hermes cron edit <job_id> --schedule "M H * * *"`, 同一批一起改; 只修一条等于留隐患。
4. 复核: 再 `hermes cron list` 读每条 `Next run`, 把下一次运行时刻换算成本地时间念给用户(别只说"已改")。
5. 顺带扫跨机作业: 要么排在开机窗内, 要么改成"按可达性门控"而不是按钟点(见 skill
   `gbrain-memory-architecture` 的 GPU 门控 + 窄窗口多跳)。跨机的活排固定钟点必然踩空。

**改一个作业的频率时, 同时复查它的保留/清理策略**: `keep N days` 的清理 + 把周期从每天改成每周 = 唯一一份产物在第 N 天被删掉, 之后长期零备份且无任何报错。产物的保留窗口要 ≥ 2-3 个新周期; 还要读一遍所有会碰同一目录的清理脚本, 确认它们的删除模式只匹配自己的文件名。详见 skill `hermes-backup-migration` 的"定时自我备份的载荷审计"。

**别设计高频轮询**(用户明确否决过"全天每 N 分钟探测一次"的方案, 哪怕每次只占资源几秒):
凡是会**短暂独占共享资源**(开库/占锁/抢 I/O)的周期探测, 收进用户点过头的一个窄窗口, 窗口外脚本
**在打开资源之前就退出**; 认可的形态是"窗口内多跳 + 目标机不在线就当天跳过", 不是"全天探测 + 回退"。
纯本地、零副作用的存活探测(如 curl 本机 :11434)不受此限。

排期依据必须实测: 任何"这台机器几点开/几点关"的说法都要有当日证据(事件日志 ID 1074/6005、
`gateway-starts.log`), 不许凭印象 —— 旧版 skill 正是照"印象里 04:00 关机"把作业排进了关机窗。

### 回答"某个时段还会跑什么 / 今晚还会不会又热又吵"——必须枚举三套调度器

只看 Hermes cron 会漏, 只看系统 crontab 也会漏。逐条查全(缺一条就会答错):

1. **系统 crontab**: `crontab -l | grep -v '^#'`。Unraid 上 root 的 crontab 在 RAM 里,
   持久化在 `/boot/config/go`, 另有 `/etc/cron.d/root`(它没有 `/etc/crontab`)。
2. **Hermes cron**: `%HERMES_HOME%/cron/jobs.json`(或 `hermes cron list --all`)。
   ⚠️ **`enabled: false` 的任务不会 fire —— 它的 `next_run` 往往停在几个月前**;
   把任务列表直接读成"将会跑"是错的, 先看 enabled 再数。
3. **systemd timer**: `systemctl --user list-timers --all`(常驻 VM 常把窄窗口任务挂这里,
   如随 GPU 门控的补嵌窗口; 它的 service 往往是"窗口外立即退出"的空转)。
4. 一次性任务若 `cron/output/<job_id>/` 里已有 "removed before firing", 不算已排。

**高温/负载归因时, 定时任务不是唯一候选**: agent 自己在那个时段做的重活(全库重嵌入排空、
批量 rclone 删除、大包压缩)一样能打满一个核并列在用户的"机器在响"清单里 —— 回答"以后还会不会热"
之前先看自己当时在干什么, 别把锅全甩给 cron。短作业还有**长热尾巴**(散热惯性),
别把尾巴当成下一次触发。

**夜间作业的准入条件**(作业跑在别人机器承载的 VM 里时): 要么走 GPU/远端算, 要么
`nice -n 19` + `ionice -c2 -n7`, 并带**窗口门控**(目标机关机就跳过)。只改排期不改载荷 =
把噪声换个时间, 问题没解决。

**收尾口径**: 说"不会了"必须同时给一条可验收的方式(次日拉该时段的温度/风扇曲线, 或任务的
`Dispatch:`/executions 记录), 并明确说出仍存在的残余风险路径(如目标机关机后的本地 CPU 兜底)。

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
