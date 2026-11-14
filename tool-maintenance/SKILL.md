---
name: tool-maintenance
description: Use when updating gbrain/hindsight or memory is full.
version: 1.0.0
author: 50.110 bot (2026-08-07)
platforms: [windows]
tags: [maintenance, gbrain, hindsight, memory, upgrade, runbook]
metadata:
  hermes:
    triggers: ["工具要更新吗", "升级 gbrain", "升级 hindsight", "版本检查", "记忆又满了", "memory full", "check tool versions", "维护记忆工具"]
    related_skills: [gbrain-memory-architecture, hindsight-local-ollama, unraid-server-ops]
---

# 工具维护 Runbook (gbrain + hindsight + 记忆分层)

50.110 上的长期记忆栈：**gbrain**（主仓库，向量库）+ **hindsight**（备用向量记忆，复活于 2026-08-07）。本技能是入口 runbook；深水区分别看 `gbrain-memory-architecture` 和 `hindsight-local-ollama`。

## 记忆分层规矩（<200 字符 vs gbrain）

- `memory` 工具 = 每轮必需品（红线、铁律、偏好、环境怪癖），2200 字符上限。
- **遇到容量警告 → STOP，把细节写进 gbrain 页面，memory 只留指针。** 绝不压缩硬塞、绝不删旧条目腾地方。
- gbrain 页面用文件方式写入（避免转义地狱）：
  ```bash
  write_file C:\tmp\page.md  # 内容
  cd ~/.bun/install/global/node_modules/gbrain && bun src/cli.ts put <slug> < /c/tmp/page.md
  bun src/cli.ts search "<关键词>"   # 验证命中（>0.9 分 = 生效）
  ```
  **前置条件：Ollama 必须在跑**（embed 依赖 localhost:11434）。没跑则 put 整笔回滚。
  一键保险（静默，已就绪就直接过）：
  ```bash
  bash ~/.hermes/scripts/ensure-ollama.sh   # 检测 11434，没跑就自动拉起并等就绪
  ```
  手动兜底：
  ```bash
  powershell -NoProfile -Command "Start-Process 'C:\Users\<user>\AppData\Local\Programs\Ollama\ollama.exe'"
  curl -s localhost:11434/api/version   # 确认
  ```
  Ollama 已配开机自启（启动文件夹 Ollama.lnk → ollama app.exe，目标有效）；没跑通常是手动退出/崩溃。

## 每 3 天自动升级(2026-08-14 起,替代每周检查)

- Cron `tool-auto-upgrade-3d`(每 3 天 09:00 `0 9 */3 * *`,no_agent watchdog,静默=全部最新):
  脚本 `~/.hermes/scripts/auto-upgrade-tools.py`(**Python 版**),检查 gbrain(GitHub releases)
  + Hermes 本体(仅提示不自动升级);**hindsight 已 2026-08-15 摘除,不再检查**。有新版就
  **自动升级**(带回滚保护),有更新才输出报告,大更新标 ⚠️。
  手动触发:`cronjob action=run` 或直接跑
  `python "C:/Users/<user>/AppData/Local/hermes/scripts/auto-upgrade-tools.py"`
- **cron 脚本必须用 .py 不能用 .sh(2026-08-14 实测)**:cron 执行器把 Windows 反斜杠路径
  (`C:\Users\...`)直接当参数传给 git-bash,反斜杠被吞 → `No such file or directory`(exit 127)。
  .py 走 Windows Python 执行器,原生接受 `C:\...` 路径,无此坑。
- 修脚本注意:GitHub API 的 tag 值在一行里出现多次(tag_name/tarball_url/zipball_url)
  → 提取必须 `| head -1`,否则变量里全是重复行导致误报。
- **升级验证必须跑 `stats`,版本号+doctor 都不够**(0.45.12.0 实测:引擎坏了 doctor 照样
  输出 health_score)。stats 报 `Cannot find module .../pglite.wasm` = pglite 链接坑(见下)。

## gbrain 升级前置:Bun 版本门槛(2026-11-14 实战踩坑)

新 gbrain 要求 **Bun ≥ 1.4.4**。版本不够时升级不会报"Bun 太旧"就停下,而是**装上新版后引擎起不来**
(stats 异常/pglite 资源链接缺失),`auto-upgrade-tools.py` 判定失败→自动回滚到旧版,报告里只写
"❌ 引擎功能验证失败(stats 异常),回滚到 vX"。看到这条先查 Bun:

```bash
bun --version                                   # 必须 ≥1.4.4
BUN_INSTALL='C:/Users/<user>/.bun' bun upgrade   # ⚠️ 必须带 BUN_INSTALL,否则装到 H:\dev\bun
```

升级后 `bun add -g` 会提示 `Blocked 1 postinstall`(gbrain 的 scripts/postinstall.ts),**不要执行
`bun pm -g trust`** ——新版 stats/doctor/search 正常就不需要它。

## gbrain 升级（0.42.8.0 → 0.42.73.2 实战，2026-08-07）

```bash
# 0) 查最新 tag
curl -s https://api.github.com/repos/garrytan/gbrain/releases/latest | grep -m1 '"tag_name"'

# 1) 升级（必须带 BUN_INSTALL 覆盖 + Windows 风格路径！）
BUN_INSTALL='C:/Users/<user>/.bun' bun remove -g gbrain        # 先删旧的（依赖循环坑）
BUN_INSTALL='C:/Users/<user>/.bun' bun add -g github:garrytan/gbrain#v<tag>

# 2) 验证
grep -m1 '"version"' ~/.bun/install/global/node_modules/gbrain/package.json
cd ~/.bun/install/global/node_modules/gbrain && bun src/cli.ts doctor --json | grep health_score
bun src/cli.ts stats && bun src/cli.ts search "<关键词>"
```

**致命陷阱（全部实战踩过）：**
- `bun add -g gbrain@latest` = 装上 npm 冒牌包（stormcolor GPU 库）！gbrain 不在 npm。
- `BUN_INSTALL="$HOME/.bun"`（POSIX 路径）→ bun 建出 `C:\c\Users\ianle\.bun` 垃圾目录。
  必须用 `C:/Users/<user>/.bun`。
- 原地升级报 DependencyLoop → 先 `bun remove -g` 再 add。
- 升级后 doctor 自动跑 schema 迁移（v112→v125，13 个迁移），数据无损。
- `bun pm -g untrusted` 查被拦的 postinstall（默认 BUN_INSTALL=H:\dev\bun 时无 lockfile 会报错，需带覆盖变量）。

## hindsight 状态：已彻底停用清理（2026-08-15 起）

**不再安装、不再检查升级、不再拉起。** 用户指令：hindsight 用不上,服务+包全清。
- 4 个 pip 包（hindsight-all/api-slim/client/embed v0.9.1）已卸载。
- `auto-upgrade-tools.py` 已摘除 check_hindsight()（备份清单：
  `~/.hermes/backups/hindsight-uninstall-20260815.txt`，含 undo 恢复命令）。
- **如用户后悔要恢复**：按备份清单重装 4 个包 + 手动加回脚本函数。
- pg0 数据目录 `~/.pg0/instances/hindsight-local/`（含 stale postmaster.pid）**保留未删**，
  如需一并清理需用户另行批准。
- 记忆栈现在只有 gbrain 一个主力，无备用。

## hindsight 升级/复活（0.6.1 → 0.8.6 实战，2026-08-07）

```bash
# 解释器：Python 3.14.6（winget 装），用户目录重定向到 H:
PY="C:/Users/<user>/AppData/Local/Programs/Python/Python314/python.exe"

# 升级（⚠️ 必须 env -u PYTHONPATH，否则 pip 把 venv 依赖当"已满足"跳过，装完 import 崩）
env -u PYTHONPATH "$PY" -m pip install --user -U hindsight-all hindsight-api-slim hindsight-client hindsight-embed

# 验证导入
env -u PYTHONPATH "$PY" -c "import dotenv, fastapi, uvicorn, hindsight_api"

# 启动服务（后台，干净环境）
env -u PYTHONPATH bash -c 'export HINDSIGHT_API_LLM_PROVIDER=ollama HINDSIGHT_API_LLM_MODEL=gemma4:26b HINDSIGHT_API_LLM_API_KEY=ignored HINDSIGHT_API_LLM_TIMEOUT=600 HINDSIGHT_API_EMBEDDINGS_PROVIDER=local HINDSIGHT_API_RERANKER_PROVIDER=local HINDSIGHT_API_DATABASE_URL=pg0://hindsight-local && /h/dev/python/Python314/Scripts/hindsight-api.exe'

# 健康 + 冒烟
curl -s localhost:8888/health    # {"status":"healthy","database":"connected"}
```

**陷阱：**
- Hermes 终端环境导出 PYTHONPATH=hermes venv → 所有 python/pip 从终端启动都被污染。
  统一 `env -u PYTHONPATH`。
- 0.8.6 API 变更：`ReflectResponse.response` → **`.text`**。
- `bash -c '...'` 启动命令会触发审批门（可能超时被拦）——提前告诉用户要点批准。
- 服务是会话后台进程，会话结束会停；要常驻需另行做计划任务。

## 验证总清单（升级后必跑）

| 项 | 命令 | 通过标准 |
|---|---|---|
| gbrain 版本 | `grep '"version"' <gbrain>/package.json` | == 最新 tag |
| gbrain 健康 | `bun src/cli.ts doctor --json` | health_score 上升、无红牌 |
| gbrain 检索 | `bun src/cli.ts search "x"` | 命中 >0.9 |
| hindsight | ~~已卸载~~(2026-08-15 彻底清理,无此验证项) | — |

## 桌面应用升级报告插件(2026-08-14)

- **最终方案 = 双门**:Python 后端在 unified 包 `plugins/tool-upgrade-report/`
  (`plugin.yaml` + `dashboard/{manifest.json, plugin_api.py}` + `__init__.py`),
  前端 UI 在 **standalone door** `desktop-plugins/tool-upgrade-report/plugin.js`。
- **关键坑:unified 包的 desktop half 强制 opt-in**(runtime-loader.ts line 238-242:
  `roots.push({ defaultEnabled: false, ... })`),即使在 plugin.js 写
  `defaultEnabled: true` 也被 root 级覆盖 → **状态栏 chip 不出现**,只有命令面板
  inventory。必须用户在 Settings → Plugins toggle,或改用 standalone door。
- **standalone door 默认启用**("keeps its default-on trust"),且 ctx.rest 按 plugin
  id 路由到 `/api/plugins/<id>/` → 同名 unified 包后端照常命中。所以
  plugin.js 放 desktop-plugins/ 即可,无需 toggle,无需重启(5s 扫描/fs-watch 热加载)。
- `hermes plugins enable <id>` 只管 Python half(plugins.enabled 数组)。
  **`hermes config set plugins.enabled` 会把数组存成字符串**(`'["..."]'`),必须用
  `hermes plugins enable`。
- desktop 插件 area id 实测:`'routes'`(ROUTES_AREA)、`'sidebar.nav'`(SIDEBAR_NAV_AREA)、
  `'statusBar.right'`。**`'sidebarNav'` 是错的**。ctx 只在 register(ctx) 回调可用,
  组件内用模块级变量持有。
- 报告文件 `scripts/last-upgrade-report.txt` 由 auto-upgrade-tools.py 维护:
  **非空=有升级报告**(chip 显示 📋 升级),**空=全部最新**(chip 显示 ⚙️)。
  页面「标记已读」POST /clear 清空文件。
- 桌面窗口状态栏 = 窗口最底部一行(网关 就绪 | ianle | 版本号),chip 在版本号左侧。
- 后端 API 需认证(curl 无 token 返回 Unauthorized 是正常);desktop 内部 ctx.rest 带 token。
- 改插件后:standalone door 文件保存即热加载;Python 后端改动需 gateway 重启。

## health_score=0 但引擎正常:两个结构性 fail(2026-11-14)

`default` 源 local_path 是 `/home/ianlee168/brain-default`(161 姐那侧的 Linux 路径),本机按设计
拒绝 sync 它 → `sync_freshness`/`cycle_freshness` 常驻 fail,brain 类拿 0 分。**不要去改这个路径**:
在非 owner host 上把路径指到本地目录,下一次 sync 会把 60 页笔记当成文件缺失而 soft-delete。
要修就在 owner host(161)上 sync/dream。本机能做的只有 gmail 源:
`gbrain sync --source gmail-ianlee168` → `gbrain embed --stale --catch-up --yes --source gmail-ianlee168`
→ `gbrain extract --stale --catch-up --source-id gmail-ianlee168` → `gbrain dream --source gmail-ianlee168`。

## 相关技能分工

- `gbrain-memory-architecture` — gbrain 全量 CLI、2-layer 规则、BUN_INSTALL/npm-squat 陷阱详解
- `hindsight-local-ollama` — hindsight 环境变量、模型选择、pg0 锁、PYTHONPATH 陷阱详解
- `unraid-server-ops` — Hermes VM(.161) 死机诊断阶梯 + destroy/start 急救 + 备份流程
