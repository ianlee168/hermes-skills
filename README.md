# hermes-skills — 多 bot 协作约定

**这个仓由 ianlee168 的多个 bot 共同维护。** 任何 bot 改 skill 前**必须**先读这页。

## 目录归属

| 目录 | 谁管 | 改前必读 |
|------|------|----------|
| `gbrain-recovery/` | 50.161 webui-hermes bot | "零硬编" 原则（不改 IP / 平台 / 绝对路径） |
| `gbrain-backup/` | 50.161 webui-hermes bot | 改 `backup.sh` 前看 `references/cron-setup.md`（如有） |
| `gbrain-ops/` | 50.161 webui-hermes bot | 14 节踩坑清单，本机专属 |
| `cloudflare-access/` | 50.161 webui-hermes bot | R2 token 创脚本，本机 rclone 路径专属 |
| `switch-model-m1-m3/` | 50.110 Windows bot | 改 `config.yaml` 路径需自己适配本机 Hermes 配置 |
| `smart-home/` | 50.1 Unraid bot（NAS 端） | go2rtc / Frigate 配置，Unraid 路径专属 |
| `istoreos-passwall-update/` | 50.110 Windows bot | PassWall 升级流程，路由器专属 |
| `istoreos-istore-package-ops/` | 50.110 Windows bot | iStoreX 商店升级报 file_clash / opkg 装不上商店包的处理，路由器专属 |
| `skill-github-mirror/` | 50.110 Windows bot | skill→GitHub 同步流程，所有 bot 适用 |
| `hermes-update-troubleshooting/` | 50.110 Windows bot | Hermes 自更新故障排查（含 ZIP fallback 清构建产物坑） |
| `stock-footage-keywording/` | 50.110 Windows bot | 卖家侧素材上架关键词（通用，非本机专属） |
| `crawl4ai/` | 50.110 Windows bot | LLM 友好爬虫 crawl4ai:评估结论、安装、抽取策略、反爬实话（通用） |
| `unraid-server-ops/` | 50.110 Windows bot | Unraid(50.1) 运维大全:user scripts / VM 救援 / docker 权限 / 插件盘点 / 备份路线;IP 保留,凭证只在 gbrain |
| `windows-bsod-watchdog/` | 50.110 Windows bot | 蓝屏取证(事件日志/WER/转储)+崩溃监控部署:故障存储段解析、Minidump ACL 坑、iLink 退避队列 |
| `ha-desktop-alerts/` | 50.110 Windows bot | 门铃/摄像头事件→电脑弹窗(WS 订阅 + 置顶窗 + 原生 Toast);常驻监听器必须跑独立 venv,否则占住 Hermes 解释器会阻断 `hermes update` |
| `sp500-etf-premium-monitor/` | 50.110 Windows bot（创建）+ 50.161（迁移执行） | 标普500ETF溢价率播报 cron 架构与 iLink 限流坑；`references/migrate-to-50161.md` 为一次性迁移清单，含主机上下文 |
| `cloudflare-d1-row-read-blowup/` | 50.110 Windows bot | D1 免费额度爆表排查与修复；Worker 上传必须带 `filename=index.js` |
| `cloudflare-workers-d1/` | 50.110 Windows bot | Workers + D1 侦察/配额分级；D1 用量按 SQL 归因（`d1QueriesAdaptiveGroups.query`），治本先加索引、不许升级套餐 |
| `hermes-cron-troubleshooting/` | 50.110 Windows bot | Hermes cron 没跑/投递失败诊断；**一次性 job 漏跑超 120s 会被删除**、工作与告警不能同一失效点 |
| `home-assistant-api/` | 50.110 Windows bot | HA REST/WS 接入与操作:令牌只在 gbrain,地址必须写全,写后回读验证 |
| `hermes-windows-bash-quirks/` | 50.110 Windows bot | Windows/MSYS 终端生存手册:门卫 9 类 block 的应对、路径翻译坑、目录 junction、测试/临时文件禁落 C 盘(默认落点 `D:\hermes-test`) |
| `laya-decision-engine/` | 50.110 Windows bot | Laya 决策引擎(PyPI `laya`)安装与使用:Windows torch 只有 CPU 版必须钉 `+cuXXX`、HF/pip 缓存禁止落 C 盘、温度未拟合=置信度不可信、英文 checkpoint 非拉丁语静默崩、中文 noul 实测偏弱(通用) |
| `laya-guard/` | 50.161 webui-hermes bot（Windows 支持文件由 50.110 补） | 三层前置护栏(本地 Laya + 窄正则 + 云端 Jev 复核)的完整部署包;**通用版:任意机器/OS 照 `INSTALL.md` 走**,零硬编;改阈值或 `patterns.py` 后必重跑 `calibrate.py`;云端 key 只放目标机 600 文件,仓里永不放。**Windows 补充**:`WINDOWS-NOTES.md`(50.110 落地实测 + 两个 Windows bug + 清单哈希的 CRLF 坑)、`laya-guard.windows.vbs`(wscript 无窗口启动)、`install-windows-task.ps1`(登录触发计划任务,注意 `ExecutionTimeLimit` 默认 3 天会掐死常驻服务) |
| `4-SKILLS-USAGE.md` | **所有人** 共同管 | 通用操作上下文，零硬编 |

## 称呼约定（陛下 2026-09-22 定，两边共用）

| 机器 | 是谁 | 怎么称呼 |
|---|---|---|
| `50.110`（Windows 台式 bot） | 110妹 | **110妹 / 西宫妹妹** |
| `50.161`（NAS 上的 Hermes VM） | 161姐 | **161姐 / 东宫姐姐** |

写提交信息、回执、README 时用这两个名字，不要再互称「同事」。

跨机 SSH：**用户名是 `ianlee168@`**（不是 `ianlee@` —— 写错会得到 Permission denied，看起来像"没授权"）。

## 改 skill 前的 3 步

```bash
# 1. 拉最新
cd /tmp/hermes-skills-check
git pull --rebase

# 2. 检查自己改的文件是否别人也改过
git status

# 3. 改完 push
git add <file>
git commit -m "..."
git push origin main
```

**如果 push 报 "rejected" 或 "conflict"**：
- **不要**用 `git push --force`（会覆盖别人的改动）
- 先 `git pull --rebase` → 解冲突 → `git push`

## 通用约定（**所有 bot 必守**）

1. **零硬编** — 不写具体 IP / OS / 绝对路径到 skill。`/home/ianlee168/` / `50.161` / `C:\Users\` / `192.168.50.1` 都是错的。
2. **gbra* 用源码** — `cd ~/.hermes/skills/gbrain && bun src/cli.ts`，**不要**用 `bin/gbrain` 编译版。
3. **不要 commit 字面 token** — `ghp_xxx` / `sk-xxx` / `R2 secret` 全部用 `<占位符>` 替换。`git diff` 时**自己**看一遍再 push。
4. **称呼** — 对陛下照写「陛下」，**不要为了脱敏把它改成「用户」**；机器人之间用 **110妹（50.110）/ 161姐（50.161）**，不要再互称「同事」。
5. **先 dry run 再 push** — 改完跑一遍相关命令验证，再 commit。陛下 4 卷 → 王牌规矩"跑通 2 遍再写进 skill"。
6. **通信通道约定（2026-09-06 定）** — Windows 台式机（50.110）侧推送一律走微信（weixin/iLink）；跑在 NAS 上的 Hermes VM（50.161）侧推送一律走 telegram。跨机迁移任务时发送通道随之切换（例：sp500 播报迁 50.161 后已改 telegram）。
7. **动过 `git reset --soft/--mixed` 之后，提交前必须 `git status` 确认暂存区是空的** ——
   留了基于旧树的 index 时，`git commit` 会把**别人的文件**一起回退/删掉。真实事故（2026-09-22 161姐 犯）：
   一次 `reset --soft` 后的提交回退了 110妹 的 6 个 skill 内容、删掉她 3 个 laya-guard Windows 文件，
   推上去才发现。补救 = 从出事前那个 commit 原样 `git checkout <sha> -- <paths>` 再提交；**别 force push**。

## 任务分工（陛下 2026-09-22 定）

| 任务类型 | 归谁 | 备注 |
|---|---|---|
| 要 GPU，或要碰本机资源（桌面 / Chrome / D: / H: / 微信 / USB） | **西宫妹妹（50.110）** | 排期必须落在 15:00–01:00 在线窗口；长任务要能中断续跑 |
| 要 24/7、深夜/清晨定点触发，或守护类（看门狗 / 巡检 / 对外服务） | **东宫姐姐（50.161）** | ⚠ 4 核 / 7.2G / 无 GPU —— 别派重活（Laya 常驻已吃 1.5–2G） |
| 两者都不要（纯网络 / 纯运维琐活） | **东宫姐姐** | 她一直在，秒级响应 |
| 同上，但数据在某台的本地盘 | **数据所在那台** | 省得跨机搬 GB 级文件 |
| 跨机迁移 / 对账类 | **谁在线谁做，发起端优先** | —— |

### 落地时的实测补充（161姐 2026-09-22 量过）

- **"定点触发"要走系统 cron，不走 Hermes 任务库**：本机 `hermes-gateway.service` 是 failed，没人 tick Hermes
  的任务队列（两处 store 心跳都停在 08:00）。真正在跑的是**系统 crontab 里那 8 个**（01:00 备份 / 03:00 脑备份 /
  08:00 auto-update+HA / 09:00 immortalwrt+lucky / 16:00 frigate / 20:00 新闻），产物连续多日出得来。
  → 派给东宫姐姐的定点活儿用**系统 cron / systemd timer** 落地最稳；要用 Hermes 任务库得先起 gateway
  （会抢 Telegram/微信 token，需陛下同意）。
- **内存比"7.2G"紧**：实测可用 ~4.6G，swap 已用 2.3G/3.8G，load ~1.4 / 4 核，Laya 常驻 1.7G。
  → 把"别派重活"量化：单任务峰值 ≲1.5G、不同时跑两个内存型任务、不常驻 >5G 的服务。
  磁盘还有 ~144G 空，暂存 GB 级文件没问题（但**跨机搬 GB 是双输**，能"就地算、只搬结论"就别搬原件）。
- **"无 GPU" 说准**：无独显、无 CUDA、torch 是 CPU 版；Ryzen 核显在（`/dev/dri/card1`）只算转码候选，别当算力。
- **"要 Chrome" 的分界线是"要不要陛下的已登录态 / 扫码 / 桌面会话"**，不是"有没有浏览器"：东宫姐姐能跑
  headless 浏览器（TypeSafe 注册就是她全流程做的），但碰不到陛下的桌面、微信通道、USB 设备。

## 谁管什么 — 解释

| 改的事 | 谁改 | 谁审 |
|------|------|------|
| `gbrain-*` 系列 | 50.161 webui-hermes bot | 陛下看 git log |
| `switch-*` | 50.110 Windows bot（如有） | 50.161 不审，直接推 |
| `istoreos-passwall-update/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `istoreos-istore-package-ops/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `skill-github-mirror/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `hermes-update-troubleshooting/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `stock-footage-keywording/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `crawl4ai/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `sp500-etf-premium-monitor/*` | 50.110 Windows bot（创建） | 50.161 按 references/migrate-to-50161.md 执行迁移后接管 |
| `cloudflare-d1-row-read-blowup/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `cloudflare-workers-d1/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `hermes-cron-troubleshooting/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `smart-home/*` | 50.1 Unraid bot（如有） | 50.161 不审 |
| `unraid-server-ops/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `ha-desktop-alerts/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `windows-bsod-watchdog/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `laya-decision-engine/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `home-assistant-api/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `hermes-windows-bash-quirks/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `4-SKILLS-USAGE.md` | **任何 bot 改都行**，但要看 | 跨 bot 改 → push 前必须 `git pull` 看别人改了什么 |

## 冲突常见场景

**场景：bot A 改了 gbrain-recovery 第 5 行，bot B 也改了第 5 行。**
```
bot A push 完（commit X）
bot B 想 push → rejected
bot B 跑:
  git pull --rebase
  # 解决第 5 行冲突（手动选 a / b / both）
  git add gbrain-recovery/SKILL.md
  git rebase --continue
  git push
```

**场景：bot A 改 gbrain-recovery，bot B 改 switch-model-m1-m3。**
- 无冲突，bot B 直接 push 成功。

## 进阶：分支工作流（如果冲突频繁）

如果冲突太多（>1 周 1 次），可以启用分支工作流：

```bash
# bot 改完 push 到自己的分支
git checkout -b bot-<name>-<feature>
git push origin bot-<name>-<feature>
# 告诉 ianlee168 在 GitHub UI 上开 PR
# ianlee168 或 webui-hermes 合并
```

**现在不用**。先按"约定目录归属 + 手动解冲突"跑。

---

## 新 bot 上岗必读

1. **不要** 直接 push 到 main
2. 先 `git clone https://github.com/ianlee168/hermes-skills.git /tmp/hermes-skills-check`
3. 改自己领域的 skill
4. push 前 `git pull --rebase`
5. push 报错就解冲突再 push

**不要** —— 看到 `git push --force` / `git reset --hard` / 直接 rm 别人文件 / 删别人 commit。
