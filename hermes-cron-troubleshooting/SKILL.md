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
   claimed_at/started_at/finished_at/status/error/delivery_outcome): `claimed_at` 远晚于计划时刻 = 补跑(catch-up)。
   - **`jobs.json` 是 `{"jobs": [...]}` 字典, 不是列表** —— `for j in json.load(f)` 拿到的是键名字符串,
     紧接着 `j.get(...)` 必抛 `AttributeError: 'str' object has no attribute 'get'`。用
     `d["jobs"] if isinstance(d, dict) else d`。
   - **no_agent 脚本作业崩了, 完整 Python traceback 就存在 `jobs.json` 的 `last_error` 和
     executions.db 的 `error` 列里**, 不用去翻日志: 读一眼就能定位到文件:行号(如
     `TypeError: string indices must be integers` @ `daily_pnl_report.py:109`)。
   - ⚠️ **`delivery_outcome: delivered` 会误导人**: no_agent 作业脚本 exit 1 时, 引擎"投递"的可能是
     一段错误信息或干脆没有正文 —— 用户端什么都没收到, 而记录看起来是"已投递"。判"用户有没有收到"
     要看 `status`(`failed` 就别信 delivery) + `cron/output/<job_id>/<ts>.md` 的正文, 不是只看 delivery。
     这类"跑了但崩了"的漏报在用户视角与"根本没跑"完全一样 —— 所以关键日报的脚本必须逐个数据源降级
     (见 skill `spot-trade-execution` 的简报脚本一条), 不能让一个接口抖动把整份报告带走。
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
- **⚠️ 汇报文本中的 URL 严防触发客户端 Context Warning**:
  若 prompt 或脚本输出中包含裸 URL 且紧贴非空白/中文标点（如 `host=http://192.168.50.110:11434/v1（队列空`），
  Hermes 桌面端的内容解析器会把括号与中文连带当成 `@url:` 上下文指令进行抓取并报错
  （`--- Context Warnings ---: no content extracted`）。
  **铁律：所有汇报中的 URL 必须用反引号包裹（如 \`http://...\`）或保证后接空格**，切勿紧贴中文字符。

## 盯 Hermes 自己的日志做看门狗(静默降级 / 凭据失败)

有些故障**不报错、只降级**(主 provider 解析失败 → 会话按 `fallback_providers` 换模型继续答),
靠人发现平均要几天。把它做成空闲零 token 的看门狗:

```bash
hermes cron create '*/20 * * * *' --name provider-fallback-watchdog \
  --script provider-fallback-watchdog.py --no-agent --deliver local
```

脚本本体: skill `hermes-agent` 的 `scripts/provider-fallback-watchdog.py`(扫 `logs/errors.log` 的
`Primary provider auth failed`,可移植到别的机器)。

- **按时间戳去重, 不按行数/偏移**: state 里存 `last_ts`, 只报 `stamp > last_ts` 的条目。用行号会在
  `errors.log` 轮转成 `errors.log.1` 之后要么重复报要么永久漏报。
- **首跑要吞历史**: 装上第一次运行会把窗口内的旧错误全算“新增”刷屏 —— 先手动跑一次让它只写 state, 再启用;
  或者首跑只落 state 不输出。
- **投递通道先证活再挂上去**: iLink session 过期时 `--deliver weixin` 会静默失败, 看门狗等于不存在。
  未验证通道前一律 `--deliver local`(桌面可见), 通道证活后再改目标。
- **验收必须做三态故障注入**: ①只放窗口外的旧错误 → 期望静默; ②追加一条当前时间的错误 → 期望告警;
  ③紧接着再跑一次 → 期望静默(去重生效)。用 `HERMES_WATCHDOG_LOG` 这类环境变量指向临时日志跑,
  别拿真日志赌。
- **要验“真作业能不能送到”就把 state 的 `last_ts` 倒回纪元**(改成 `"2000-01-01 00:00:00"`, 再 `hermes cron run <id>` + `hermes cron tick`):
  cron 作业注入不了 `HERMES_WATCHDOG_LOG` 这种环境变量, 而倒回 state 能让现有真日志行重新算作“新增”,
  端到端走一遍 脚本→引擎→投递通道; 测完脚本会把 state 写回最新值, 不必手工复原。
  判定看 `cron/jobs.json` 的 `last_status`/`last_delivery_error`、`cron/output/<job_id>/<ts>.md` 的正文,
  以及 `hermes cron list` 那句 `Last run: … ran, but the result was not delivered (delivery error: …)`。
- 这类“内容判据”看门狗同样要防"尾部陈旧"(见下一节): 判据是**带时间戳的新增条目**, 不是文件尾部。

## 巡检/看门狗判「日志尾部报错」前, 必须验证尾部内容是不是最近一次运行写的

**症状**: 巡检天天报同一条异常, 打开日志发现那行错误是几天/几个月前的; 而任务本身健康(心跳 rc=0)。或者末行明明白白写着 `OK`，巡检却报「日志尾部报错 ['error', 'failed']」。

**两种陈旧尾部失效模式**:
1. **模式 A（静默作业日志不动）**: 「静默=健康」的作业（只在异常时写日志）日志 mtime 长期不动，而巡检只看**文件尾部 400 字节** → 一条历史告警行被永久当成现状。2026-10-11 实例: 161 的 `cron_health_check.py` 判据③ 把 `ha_daily.log` 里 10-05 那条真告警当成现状天天报；同批发现 lucky / frigate 同样陈旧。
2. **模式 B（短输出吞入前次历史）**: 作业健康时写出单行简短状态（如 `[TS] OK router=...` 88 字节），日志 mtime 完全新鲜（lag ≈ 0），但固定的 400 字节窗口向前跨过了本次运行的起点，截入了上一轮的旧报错、Traceback 或推送助手的降级日志（如 `[Weixin] FAILED: ...`）→ 导致关键字匹配到 `error`/`failed`，出现「提取末行是 OK，整体却报 BAD」的自相矛盾。

**修法**(已落地在 161 `~/.hermes/scripts/cron_health_check.py`):
1. **比对心跳与 mtime 防模式 A**: 有心跳时用**日志 mtime 与心跳 epoch 比对** —— 日志 mtime 早于最近一次运行超过 0.5h 即判定尾部陈旧，跳过该判据，并在 OK 行里写明「已跳过尾部判据」(别静默省略)；无心跳时回退到「日志 mtime 超过允许静默时长就不判」。
2. **时间戳边界切片防模式 B**: 当日志尾部判定新鲜时，若尾部文本存在时间戳标记（正则 `(?:^|\n)\[?20\d\d[-\.]\d\d[-\.]\d\d[^\n]*`），**只截取最后一个时间戳之后的内容**（`run_tail = tail[m[-1].start():]`）作为本轮输出进行错误关键字匹配。任何在最后时间戳之前的文本都属于上一次运行，必须剔除；无时间戳时才回退使用整段 tail。
3. 真失败由**心跳 rc** 那一档负责，所以跳过尾部判据或切掉历史日志绝不会漏报（作业退出码非 0 一定被抓）。

**验收**: 必须做故障注入测试 —— ① 陈旧尾部+rc0（期望跳过）；② 新鲜单行OK+前接历史error+rc0（期望OK，切片生效）；③ 新鲜尾部含真实error+rc0（期望报错）；④ 新鲜尾部+rc1（期望报错）。

**通用规则**: 凡是拿「文件内容/尾部」当判据的看门狗, 都要同时判「这段内容是谁、什么时候写的」。
只看内容不看时间 → 把历史事件当成常态; 只看时间不看内容 → 把「静默」当成健康。固定窗口大小（如 400 字节）必须配合分界符/时间戳切片，绝不可假设本次输出一定填满该窗口。

## 停用一条 cron 行 ≠ 停用巡检: 巡检的 JOBS 清单必须从 crontab 反推

**症状**: 某作业早就从 crontab 注释掉了(或根本没装), 巡检却天天报「心跳已静默 N 天 ← 可能已挂」, 一报十几天。

**根因**: 健康巡检脚本里有一份**手写的期望作业清单**(161 `cron_health_check.py` 的 `JOBS`)。它是第二份登记表,
与 crontab 两处分别维护 → 停用作业时只改 crontab, 清单里那条永远拿不到心跳, 必然永久 BAD。
2026-11-13 实例: immortalwrt 检查整行被注释(理由写「虚拟机已关闭」, 但该脚本 10-22 起改查 iStoreOS 路由器), 停用 12 天期间漏报了一次路由器重启。

**修法**: 巡检开头读 `crontab -l`, 剥掉 `#` 开头的行, 正则取 `cron_hb.sh <tag>`, 得到"活作业集合";
`JOBS` 里 tag 不在集合内的直接归 `[SKIP] …(crontab 中已停用, 跳过巡检)`, 不参与判据。
以 crontab 为唯一真相后, 停用/改排期都不用再同步第二份清单; 读不到 crontab(返回 None)时退回原逻辑, 不能变成"永远不报"。

**顺手要做的两件事**:

1. **停用一条作业前先读一遍它到底在检查什么**。注释里写的理由可能是旧印象(本例把"检查 iStoreOS 路由器"当成"检查早已下线的 ImmortalWrt 虚拟机")。
   确认停用是有意的, 再同时处理巡检清单。
2. **兜底通道自己也要被巡检**。crontab 里那些防"Hermes provider 挂掉"的系统级兜底作业(如 08:05 的 Unraid 日检)如果不进 `JOBS`,
   它挂了也没人知道 —— 兜底就变成只有一层。

**新增作业进 JOBS 前先看它的日志尾部会不会误命中 ERR_MARKS**: 典型是通知助手成功走了 Telegram 兜底, 日志里仍留着
`[WeChat 通知失败] …` / `(weixin failed: …)`, 命中 `failed` → 新作业一上线就假 BAD。
给每个作业留一个 `tail_ignore` 正则列表, 在错误关键字匹配**之前**把这些已知无害的行剥掉; **别全局屏蔽**这两个词, 别的作业里它们是真错。

**验收要真注入**: 临时把某条 cron 行加前缀注释 → 跑一次巡检, 期望出现 `[SKIP]` 且退出码 0; 随后在 `finally` 里恢复 crontab 并**逐字比对 `crontab -l` 与原始内容是否 IDENTICAL**(别只信"已恢复")。

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
5. **脚本必须自带四件套**(缺任何一件都会以"看起来正常"的方式坏掉):
   ①**每一步子进程都加显式超时** —— 作业级默认超时 3600s, 而超时后 rclone/du/find 这类子进程
   可能变孤儿继续跑、继续占 I/O; ②**并发锁** —— 锁文件里写 `pid=`, 判"陈旧"只看"pid 还活着吗
   + 时限", **绝不删锁文件**(删除一律要用户授权); Windows 判活用
   `ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)`(拿到句柄即存活, 顺便 CloseHandle),
   不要用 `os.kill(pid, 0)`; ③**追加式回执日志**(每行记 rc/耗时/报告), 次日能一眼看趋势;
   ④**退出码语义固定**: 0 成功 / 1 真失败 / 3 已有一个实例在跑(别让它被当成失败)。
6. 起步骨架(含上面四件套 + 良性错误分类)见 `templates/no_agent_job_script.py`: 复制到
   `$HERMES_HOME/scripts/`, 只改顶部 CONFIG 与中间的 WORK 两段。

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
第三类要单独识别: **活库写入竞态** —— `corrupted on transfer: md5 hashes differ` 出现在正在被写的文件上
(mongo journal / WiredTiger / `*.partial` / `*.wal` / `*.shm`), 源在读取与校验之间又被追加了。rclone 会拒绝
这份拷贝(不会写出坏数据), 下次运行自然重试。判定规则要**同时看错误类型和路径**: 只有"哈希不符 + 路径属于
活写区"才容忍, 其它路径的哈希不符必须报失败 —— 那才是真损坏或被静默替换的文件。
容忍类也要把计数和文件名写进日报, 否则"容忍"就变成了"看不见"。

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

**但 config 顶层的 `cron.model` / `cron.model_provider` 是整个 profile 的总闸, 换模型/换上游时必须逐 profile 复查。**
那两行不在 `jobs.json` 里, `hermes cron list` 也不显示, 却钉住**该 profile 下所有没单独钉模型的作业** ——
上游账号/渠道一挂(403/401/模型下线), 这个 profile 下的每个 cron 会话就一起报同一个上游错误,
而逐条看 `jobs.json` 的 `model` 字段全都"正常", 极易误判成单条作业的毛病。
排查顺序: 先 `grep -n -A4 '^cron:' ~/.hermes/config.yaml`(以及 `~/.hermes/profiles/*/config.yaml`)
看这两行的值还活不活, 再查单条作业。改完**必须重启该 profile 的 gateway**(启动时读一次),
并用该 profile 跑一条 `hermes --profile <p> -z "ok"` 证明新上游真能通。
同一网关常被多台机器共用 —— 换模型时把每台机器的每个 profile 都扫一遍, 只改一台等于留一排定时报错。
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
- **多通道兜底通知助手（如微信+Telegram）绝不能因主通道环境异常崩溃**:
  主通道（微信 iLink / gateway platform API）调用必须置于全覆盖 `try...except` 之下，并在调用前显式检查依赖（如当前 python 是否安装 `aiohttp`、凭据是否存在）。若主通道因缺少第三方库抛出未捕获异常（如 `AttributeError: 'NoneType' object has no attribute 'ClientSession'`），会导致 Python 进程直接 crash，下游备用通道（Telegram）和本地 pending 落盘逻辑被彻底绕过，告警静默丢失且触发 cron `rc=1`。
- **通知调用切忌在脚本内加 `>/dev/null 2>&1`**:
  很多 check 脚本习惯在调用通知助手后加 `>/dev/null 2>&1`，这会彻底抹掉通知失败的 traceback 或回执；crontab 最外层已有日志重定向，放开 stderr/stdout 才能在 cron 日志里看清“OK sent via telegram”或具体崩溃堆栈。
- **“健康静默”型脚本的潜伏缺陷：告警代码路径平时不跑**:
  “平时 OK/静默，仅异常时告警”的脚本，其告警分支代码可能数月不被触发。必须自带自测/故障注入开关（如 `ROUTER_NOTIFY_DISABLE=1` 或注入假指标测试分支），验证告警分支的语法、参数传递、通知退出码与日志输出，防止真正出事故时因通知崩溃而雪上加霜。
- 完整实例与迁移执行清单: skill `sp500-etf-premium-monitor`。

## 改 cron 脚本本身: 重试、真假成功判据、故障注入验收

给"自动更新/自动部署"类的 cron 脚本加健壮性时, 三件事必须一起做, 否则改完只是看起来更好:

**① 重试要围绕"最脆的那一次外部命令", 而不是整段脚本从头再来。**
很多上游命令自带硬超时(典型: 解析 release tag 的那次 `git ls-remote`, 内部 60s 就放弃),
一次网络抖动就让整轮作废 —— 而同样的命令几十秒后重跑 1 秒就返回。加一档"首次失败 → 只记日志、`sleep 300` → 重试一次 →
两次都失败才通知"即可, 前提是重试**幂等**: 代码没动时更新是空操作; 首轮已拉下代码但后续步骤(依赖同步/服务重启)挫败时,
重试只是把它补完。设计时把"第一次失败"和"最终失败"写成两种日志语气, 让巡检/自己一眼能分辨是自愈还是真坏。

**② 成功判据必须是"产物真的变了", 不能是命令退出码。**
自动更新类脚本最常见的谎报: 上游分支领先几千个 commit, 而实际通道(release tag)早已是最新 → 命令退出 0、什么都没装,
脚本却照着 `HEAD..origin/main` 的 commit 数打印"已更新 N commits", 于是每天推一条假进展, 真故障反而被淹没。
规则: **比前后 SHA/版本号** —— 相等就记 `up-to-date(通道 vX @ sha; 上游分支另有 N 个未发布 commit, 属正常)` 且**不推送**;
不相等才发"已更新"。判断"到底落后没有"要用工具自己的权威口径(如 `hermes update --check`), 不是 `git rev-list --count`。

**③ 验收必须故障注入, 而且注入的是"真脚本里那一段代码", 不是你复述的逻辑。**
- 从真脚本里**切出被测块**: 按注释里的分节标记(`# --- x ---`)把其它段落裁掉, 保留 preamble + 被测块, 这样跑的仍是线上那份代码;
  别照抄逻辑到测试脚本里 —— 抄出来的一改就不再等于线上, 测了个寂寞。
- **路径用 env 覆盖, 不要 sed 改真脚本**: 预先让脚本支持 `${TEST_VENV:-...}` / `${TEST_LOG:-...}` 这类可覆盖变量(或测试时注入), 状态/日志一律落 `/tmp`。
- **缩短等待、强制进分支**: `sleep 300`→`sleep 3`; 把"要不要走这条分支"的判据临时改成 `if true`(以及把"服务在跑吗"改成 `if false &&`), 才能命中更新/重试那条路径。
- **假二进制 + 计数器文件**驱动多态: 第 N 次调用读计数器决定成败, 另留一个 `always_fail` 标记文件跑"全失败"变体。两条都要跑:
  一次失败后成功 → 期望日志出现"第 1 次失败 → 重试 → 第 2 次成功(已自愈)"且通知恰好 1 条; 一直失败 → 期望"连续两次失败"且通知恰好 1 条(不是两条)。
- 跑完读**日志行 + 调用次数文件**, 用"通知条数"和"调用次数"验收, 而不是看终端最后一行。

**④ 改「告警判据」本身时, 三件事必须一起做: 去重口径、绝对下限、换趋势文件。**
- **测量值天然翻倍先找重复源, 别急着抬阈值。** 典型: 同一个账号被集成注册了两次 → 每个实体存在 `x` 与 `x_2` 两份,
  不可用数、状态数、写入量全部 ×2。判据要**先按实体/设备去重再比**, 抬阈值只是把翻倍掩盖掉, 真实翻倍永远治不好。
- **基线只有个位数到十几时, "比中位数涨 N%" 永远先被一两个设备的正常抖动命中** → 必须再加一个**绝对下限**
  (`count >= FLOOR` 才允许告警), 否则巡检天天响、真故障被淹没。下限与百分比两条是**与**关系, 不是**或**。
- **口径一改, 历史趋势文件里的旧样本就是另一个口径** → 趋势/基线换一份新文件(旧的留着备查, **不要删**),
  否则新旧样本混进同一个中位数, 改动后头几天判据算出来是错的。状态行要同时打印"新口径/原始值/下限/中位"便于核对。
- **消息里的"时间"几乎总是检查时刻, 不是事件时刻。** 靠"与上次存的状态比对"发现的事件最多滞后一整个周期
  (日报/日检尤其), 用户在 08:00 收到一条"宿主重启过"可能指的是昨天中午的事。命中时要把**事件自己的时刻**
  (远端 `who -b` 的引导时间、实体的 `last_changed`、容器 `StartedAt`) 抄进正文, 否则用户和你都会读成"刚刚发生"。

**⚠️ 复跑一个自带发送逻辑的脚本 = 真的会给用户发消息。**
巡检/日报脚本通常在末尾自己调通知助手, 所以任何手工复跑都会推一条(测试数据里的"前次在线 34.7d"之类会被用户当真)。
复跑前把状态文件/日志/通知目标指向临时路径, 并先找脚本里的"禁用通知"开关; 没有开关就像本次一样**事后如实告知用户
"测试时真的发了一条, 正文里 X 是编的"**, 别装没发生。

**换掉远端那支脚本本身时,走「取回本地改 → 落盘校验 → 备份 → 推回 → 双向 md5」,不要就地 sed:**
```bash
scp host:.hermes/scripts/x.sh D:/hermes-test/host/            # 1 取回
#    本地用 python 按 # --- 分节标记 或 index() 切片改(ssh+sed 会被引号/反斜杠/脱敏三道咬)
bash -n x.sh                                                 # 2 本地语法
ssh host "cp -a ~/.hermes/scripts/x.sh ~/.hermes/scripts/x.sh.bak-$(date +%Y%m%d-%H%M%S)-<原因>"  # 3 远端可回滚备份
scp x.sh host:.hermes/scripts/x.sh && ssh host 'md5sum ~/.hermes/scripts/x.sh; bash -n ~/.hermes/scripts/x.sh'
md5sum x.sh                                                  # 4 两侧一致才算推成功
```
- **别拿工具回显的文件内容当真相**:含 token 的行会被脱敏成 `Bearer ***`,照它写 old_string / `str.replace(...)` 必然匹配不到(文件其实一字没坏)。锚点选不会被脱敏的结构(命令名、上下文行、`# --- 分节 ---`),或用 `s.index("关键词")` 切片替换。
- 备份名里带上改动原因(`-pre-dedupe` / `-pre-retry`),几个 .bak 并存时自己和用户都能一眼对上是哪次改动。
- 改完立刻跑一次**真实**运行看状态行(不是只看 `bash -n`);它会碰真渠道,提前把状态/日志指到临时路径(见上节)。

## 微信 iLink 专属坑

- `hermes send` **非 --json 模式失败时退出码 1 且 stdout/stderr 全空**(错误只在 --json 里)
  → 任何包了 hermes send 的脚本必须用 --json 并解析 error, 否则诊断抓瞎。
- **`ret=-2 errmsg=prepare failed`（会话未就绪）**:
  报错 `iLink sendmessage session not ready: ret=-2 errcode=None errmsg=prepare failed — the user must send the bot a message first (or re-pair)`。
  根因：iLink 微信通道过期失效或网关重启后缺乏上行 session 上下文，微信禁止单向冷启动推送。
  恢复：**切勿盲目重启网关或重新扫码**。只需让用户在微信客户端主动向 Bot 发送任意一条消息（如回复“1”），网关收到上行事件即可立即刷新 token 并恢复下发通道。
- iLink 风控是通道级的, 窗口可达小时级; 风控期间连发必 ret=-2。
  同一微信号两个 gateway 长连接会互踢(迁移通道前先确认)。
- 手动验证通道: `hermes send --list`(看可用目标)、`hermes send -t weixin --json "test"`。
