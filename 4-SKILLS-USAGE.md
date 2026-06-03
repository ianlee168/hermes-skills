# 4 卷使用说明（任何 bot 读 SKILL.md 前先看这个）

> 你已拉 4 卷 SKILL.md 到本地。**但只有文档没有脑是不行的**。
> 这一段告诉你 4 卷的真实使用场景和顺序。

## 1. gbrain 在哪（**通用判断**）

**gbrain 是 ianlee168 的"真脑"**——一个 PGlite 数据库 + 引擎 binary + 配置文件。

**怎么判断本机是不是有脑：**
```bash
# 1. 看 PGlite 数据目录是否存在
ls ~/.gbrain/brain.pglite 2>/dev/null && echo "✅ 本机有脑" || echo "❌ 本机无脑"

# 2. 看 gbrain 引擎是否可跑
cd ~/.hermes/skills/gbrain && bun src/cli.ts doctor 2>&1 | head -3
# ✅ 有 brain score 输出 = 引擎在
# ❌ "command not found" / "no brain" = 引擎或数据不在
```

**如果本机有脑** → 你能直接 query / put / extract 脑内容。
**如果本机无脑** → 你是"指挥棒 bot"，重要操作转给有脑的机器跑（具体哪台问 ianlee168）。

## 2. 4 卷的真实用途（**与平台/IP/路径无关**）

| skill | 作用 | 调用时机 | 触发信号 |
|-------|------|---------|----------|
| `cloudflare-access` | 创 R2 API Token | 备份目的地首次配置 / 凭据失效 | "备份失败" / "R2 token expired" |
| `gbrain-backup` | 脑定时备份 | 配 cron 每天自动跑 | 配一次后无需再管 |
| `gbrain-recovery` | 从备份恢复脑 | 脑坏 / 换机 / 失忆 | "brain broken" / "换机" / 任何 bot 失忆 |
| `switch-model-m1-m3` | M1 / M3 模型切换 | ianlee168 说 "M1" 或 "M3" | 直接改 `model.default` |

## 3. 调用顺序

```
cloudflare-access → gbrain-backup → (cron 跑) → gbrain-recovery → switch-model-m1-m3
              ↓                          ↓                ↓
        创 R2 token              备份脑数据          恢复脑数据
```

**前置：cloudflare-access 必须先跑一次**（拿到 R2 token），否则 gbrain-backup 没目标。
**之后 gbrain-backup 配 cron 每天自动跑**。
**gbrain-recovery 是出问题时用**（脑坏、换机、失忆）。
**switch-model-m1-m3 是任何时候 ianlee168 说"M1"/"M3"时用**。

## 4. 怎么用 gbrain（**前提：本机有脑**）

```bash
# 看健康分
cd ~/.hermes/skills/gbrain && bun src/cli.ts doctor

# 查 page（按关键词）
cd ~/.hermes/skills/gbrain && bun src/cli.ts query "GitHub PAT"

# 写 page（自动 embed + extract links）
cd ~/.hermes/skills/gbrain && bun src/cli.ts put <slug> --content "..."

# 看脑里 page 列表
cd ~/.hermes/skills/gbrain && bun src/cli.ts list
```

**`bun src/cli.ts` 是真正入口**——编译版 `bin/gbrain` 是坏的，别用。

## 5. 怎么用 backup / recovery（**前提：本机 rclone 已配**）

```bash
# 跑手动备份
~/.hermes/skills/gbrain-backup/backup.sh

# 看 cron
crontab -l | grep gbrain

# 从备份恢复（需 rclone 已配 + 知道备份在哪）
rclone copy <remote>:<bucket>/gbrain-latest.tar.gz /tmp/
tar -xzf /tmp/gbrain-*.tar.gz -C <brain-data-dir>
```

**rclone 配啥 remote / 在哪个 bucket 取决于 ianlee168 的云账号**——不是 bot 决定的，**问 ianlee168**。

## 6. hindsight 是什么

**hindsight = ianlee168 早先的"对话记忆"项目**（独立于 gbrain）。功能：
- 抓 gbrain 之外的对话历史（Slack/Telegram/X 等）
- 是 gbrain 的"上游"数据源（hindsight 抓 → gbrain ingest）

**怎么判断本机有没有 hindsight：**
```bash
# 看 .hindsight 目录
ls ~/.hindsight/ 2>/dev/null && echo "✅ 已装" || echo "❌ 未装"

# 看 hindsight 命令
which hindsight 2>/dev/null && hindsight --version
```

**没装就是没装**——不需要 bot 自己 `pip install`，**问 ianlee168**要不要装。

## 7. 关键约束（**任何 bot 必守**）

- **脑里数据安全 > 涨分**。删任何东西前先确认 + 留 undo。
- **OAuth 原始 token 不进 agent context**。所有 Google / social API 走 ClawVisor（如果配置）；不配就走本地 OAuth 文件。
- **所有 gbrain 命令必须 `cd ~/.hermes/skills/gbrain && bun src/cli.ts ...`**，**不要**用 `bin/gbrain` 编译版。
- **跨 profile 写文件会被软拦**——ianlee168 让你改哪个 profile，明确说"改 default" 或 "改 webui-hermes"，不要自己挑。
- **ianlee168 铁律：先查证再答**。"现在多少分" = 跑 `doctor`；"备份正常吗" = 跑 `tail` + `rclone lsl`。**不要靠记忆/脑测给数字**。
- **不要硬编 IP / OS / 路径**——本说明明文不写"50.161 在哪"、"Windows 用 C:\..."。不同 bot 自己看 `~/.gbrain/` 在哪。

## 8. bot 怎么停止"傻傻的"

读完这 8 段 + 4 卷 SKILL.md，你**应该会**：
- 听 ianlee168 说"M1" → 读 switch-model-m1-m3 改 `model.default`
- 听 ianlee168 说"备份" → 跑 `~/.hermes/skills/gbrain-backup/backup.sh` 或看 cron
- 听 ianlee168 说"多少分" → 跑 `bun src/cli.ts doctor`
- 听 ianlee168 说"恢复" → 读 gbrain-recovery 走 4 步
- 看到 4 卷就位 → 问"本机有脑吗 / hindsight 装了吗 / rclone 配了吗"，**别假设**

**你**不会**的事（合理拒答 + 转给 ianlee168）**：
- "本机没脑怎么恢复" → 答"本机没脑可恢复，要先从有脑的机器拉备份或让有脑机器跑"
- "rclone 怎么配" → 答"rclone 配啥 remote 是 ianlee168 云账号的事，请他提供 token 或他跑"
- "hindsight 怎么装" → 答"hindsight 没装是事实，ianlee168 决定要不要装"
- "我能在 50.161 跑吗" → 答"不知道 ianlee168 在哪台机器有脑，**问**他"

**该问 ianlee168 的事**：
- "本机是不是脑主？还是 ianlee168 让我去别处跑？"
- "R2 / Drive 凭据他配在哪？"
- "hindsight 装没装？要不要装？"

**别假设，**先问清楚再行动**——别把"50.161 是脑"当默认值**。
