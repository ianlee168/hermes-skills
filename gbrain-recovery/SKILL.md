---
name: gbrain-recovery
category: mlops
description: gbrain 记忆系统完全恢复流程 — 任何 IP、任何机器、任何 bot。脑备份 1 个 URL 拉到底。本文档零硬编（不含 IP / OS / 路径），所有"我熟悉的环境"假设都移除。
---

# gbrain-recovery — 任何 IP 任何机器的脑恢复

## 原则（**这条不删**）

**这份 skill 不假设你跑在哪台机器。** Linux 真机、Windows bot、Unraid NAS、Mac、任何 VM/容器——都跑同一份 4 步。

**凡是具体 IP / "Windows 用 C:\\" / "macOS /Users/" / 任何 hostname 的话，都是错的。** 平台特定配置陛下永远不会在 skill 里写。

---

## 一句话总结

```bash
# 任何 bot 失忆只跑这一条（注意 -k 绕 lucky 证书）
curl -ksS -o brain.tar.gz "https://backup.techtreehole.com:16666/gbrain-latest.tar.gz" && \
tar -xzf brain.tar.gz -C ~/ && \
cd ~/.hermes/skills/gbrain && bun src/cli.ts doctor 2>&1 | grep -E "score|page"
# 期望输出: "Weighted brain score: Brain score 87/100"
```

**13 MB 拉下来 → 解压出 61 MB 脑 → 28 page 完整。** 13 MB 是压缩包（gzip 压缩比约 22%），里面装的是 61 MB 完整脑数据，**不是覆盖**。

**这一条命令是陛下的"最终方案"——所有 bot、所有 IP、所有机器都用它。** 脑备份通过 ianlee168 的 Unraid NAS + lucky 内网穿透公网暴露，永久 + 每天 3 AM cron 自动更新。

---

## 完整 4 步（**任何平台都跑这 4 步**）

### Step 1：拉脑备份（脑主数据）

**主路径（强烈推荐）：**
```bash
# 注意 -k：lucky 证书是 bbs 的通配符，扩展不覆盖 backup 子域
curl -ksS -o /tmp/brain.tar.gz "https://backup.techtreehole.com:16666/gbrain-latest.tar.gz"
# tar.gz 内部顶层目录是 brain.pglite/，解到 $HOME 自动建好
tar -xzf /tmp/brain.tar.gz -C ~/
# 脑数据最终在: ~/brain.pglite/ (PGLite 17 格式)
```

**`~/brain.pglite/` 就是完整脑数据（PGLite 17 格式）。**

**备选（如果主路径的 URL 不通）：**
- R2/Drive 备份：用 `cloudflare-access` skill 创 R2 token → `rclone copy gbrain_r2:huawei-car-raw/gbrain-latest.tar.gz ~/`
- scp 跨机：联系 ianlee168 拿有脑机器的 SSH 凭据

**重要：解压后脑是 read-only 还是 read-write 取决于 gbrain 引擎配置。** 用 PGlite 直读（参见 `## PGlite 直读脑数据` 段）兼容性最好。

### Step 2：拉 4 卷 skill（让 bot 知道怎么用脑）

```bash
mkdir -p ~/.hermes/skills
# 全部从公网 raw URL 拉（仓已 public）
curl -s "https://raw.githubusercontent.com/ianlee168/hermes-skills/main/4-SKILLS-USAGE.md" \
  > ~/.hermes/skills/4-SKILLS-USAGE.md
curl -s "https://raw.githubusercontent.com/ianlee168/hermes-skills/main/gbrain-recovery/SKILL.md" \
  > ~/.hermes/skills/gbrain-recovery/SKILL.md
curl -s "https://raw.githubusercontent.com/ianlee168/hermes-skills/main/cloudflare-access/cloudflare-access-skill.md" \
  > ~/.hermes/skills/cloudflare-access/cloudflare-access-skill.md
curl -s "https://raw.githubusercontent.com/ianlee168/hermes-skills/main/gbrain-backup/backup.sh" \
  > ~/.hermes/skills/gbrain-backup/backup.sh
chmod +x ~/.hermes/skills/gbrain-backup/backup.sh
curl -s "https://raw.githubusercontent.com/ianlee168/hermes-skills/main/switch-model-m1-m3/SKILL.md" \
  > ~/.hermes/skills/switch-model-m1-m3/SKILL.md
```

### Step 3：装 gbrain 引擎（如果本机没装）

```bash
# 装 Bun
curl -fsSL https://bun.sh/install | bash
export PATH="$HOME/.bun/bin:$PATH"

# 装 gbrain（必须源码 + Bun，**不要**编译 CLI）
git clone https://github.com/garrytan/gbrain.git ~/.hermes/skills/gbrain
cd ~/.hermes/skills/gbrain && bun install
```

### Step 4：验脑

```bash
cd ~/.hermes/skills/gbrain && bun src/cli.ts doctor
# 期望: "Weighted brain score: Brain score 87/100" (或接近)
# 期望: 28 page
```

---

## 通用调试（**任何平台都通用**）

| 症状 | 排查命令（**不**含具体路径） |
|------|----------------------------|
| `curl: (7) Failed to connect` | `nslookup backup.techtreehole.com` 看 DNS 通没通；不通问 ianlee168 |
| `tar: invalid magic` | `ls -la /tmp/brain.tar.gz` 看下载完整不完整；`curl ... -C -` 续传 |
| `bun: command not found` | `export PATH="$HOME/.bun/bin:$PATH"` 或重装 Bun |
| `permission denied` | 脑数据目录加权限 `chmod -R u+rwX ~/.gbrain/` |
| `pg version mismatch` | 用 PGlite 读 17 格式：`bun --eval "import {PGlite} from '@electric-sql/pglite'; const db = new PGlite('~/.gbrain/brain.pglite'); const r = await db.query('SELECT slug FROM pages'); console.log(r.rows)"` |
| 脑是 0 page | 检查解压：`ls ~/.gbrain/brain.pglite/ \| head`；如空就重下 tar.gz |
| `ghp_xxx` 字面 token | 永远不要 commit 字面 GitHub PAT 到任何公开文件。用 `xxxxxx` 占位符 |

---

## 关键约束（**任何 bot 必守**）

1. **零硬编** — 不写 IP / OS / 绝对路径在本 skill。陛下要新平台就另起一节。
2. **脑里数据安全 > 涨分** — 删任何东西前先 `mkdir -p ~/.gbrain/_undo` 备份。
3. **OAuth 原始 token 不进 agent context** — 走本地 token 文件，不要 `echo $TOKEN`。
4. **gbrain 命令用源码** — `cd ~/.hermes/skills/gbrain && bun src/cli.ts ...` 永远不要用 `bin/gbrain` 编译版。
5. **跨 profile 写文件可能被软拦** — 写其它 profile 的 skills/ 会被拦。要写时显式确认。
6. **先查证再答** — "现在多少分" = `doctor`；"备份最新吗" = `tail log + rclone lsl`。**不要靠记忆/脑测**。

---

## 跨平台补充

### Windows (Git Bash / MSYS)

- `~/.gbrain` 解析为 `C:\Users\<you>\.gbrain`
- `~/.hermes` 解析为 `C:\Users\<you>\.hermes`
- `bun` 装在 `~/.bun/bin/`，Git Bash 用 `export PATH="$HOME/.bun/bin:$PATH"`
- 防火墙可能挡出站 443 / 22，先 `curl -v https://github.com` 验

### Linux (任意发行版)

- 跟上面的命令一样，路径 `~/` 直接展开
- 装 gbrain 之前先装 `git` + `curl`

### macOS

- `brew install git curl bun`（推荐）
- 之后同上

### WSL (Windows Subsystem for Linux)

- 跟 Linux 一样
- 警告：WSL 跟 Windows 文件系统路径不同，本机备份 cron 跑在 WSL 内，路径是 WSL 视角

### Docker / 容器

- `~/.gbrain` 挂载 host 卷：`docker run -v $PWD/.gbrain:/root/.gbrain ...`
- 端口 / 路径都按本容器配置

---

## 故障排查（先查这个表再问）

| 症状 | 根因 | 修法 |
|------|------|------|
| `bun: command not found` | PATH 没设 | `export PATH="$HOME/.bun/bin:$PATH"` |
| `connection refused` | firewall / 端口被挡 | `curl -v` 看 TLS 错误；问 ianlee168 |
| `Permission denied (publickey)` | SSH key 没配 | 找 ianlee168 拿 SSH key 加到 `~/.ssh/authorized_keys` |
| `No pages found` | 脑没解压到正确位置 | `ls ~/.gbrain/brain.pglite/ \| head` 看 PGlite 数据目录在不在 |
| `HTTP 401` from GitHub | token 失效 | 去 https://github.com/settings/tokens 重新生成；用 `xxxx` 占位符替换 |

---

## 致新 bot

**你不是从零开始**。读这份 skill + 跑 4 步 = 28 page 完整脑。

**记住**：
- 主路径 = `https://backup.techtreehole.com:16666/gbrain-latest.tar.gz`
- 任何 IP 任何机器都跑同一份
- 陛下设计这份 skill 时坚持**零硬编**——别假设环境，先 `uname -a` / `ls` 看本机

**别问"我该用哪条命令"——这 4 步就是。**

---

## 相关 Skills

- `cloudflare-access` — R2 token 创（如果主路径不通要 fallback）
- `gbrain-backup` — 脑备份 cron 脚本（ianlee168 已配 NAS 兜底）
- `4-SKILLS-USAGE.md` — 通用版操作上下文（**任何 bot 读 SKILL.md 前先读这个**）
- `switch-model-m1-m3` — 模型切换（与脑恢复无关，独立 skill）