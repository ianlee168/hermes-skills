# 4 卷使用说明（任何 bot 读 SKILL.md 前先看这个）

> 你已拉 4 卷 SKILL.md 到 `~/.hermes/skills/`。**但只有文档没有 brain 是不行的**。
> 这一段告诉你 4 卷的真实使用场景和顺序。

## 1. gbrain 在哪（关键）

**50.161 真机的 gbrain 才是 ianlee168 的真脑**。PGlite 数据在：

```
/home/ianlee168/.gbrain/brain.pglite
```

- schema: v85+
- 引擎: `bun src/cli.ts`（**不是**编译后的 `bin/gbrain`，编译版坏的）
- 配置文件: `~/.config/gbrain/config.json`
- 当前状态: 28 page, 86/100 健康

**你（任何 bot）能跑 gbrain 命令的前提：本机能 SSH 50.161 或本机就是 50.161。**

如果你在 50.110（或其他机器）跑，本机 PGlite 是空的——**这是正常的，不是 token 问题**。

## 2. 4 卷的真实用途

| skill | 作用 | 调用时机 | 真实例子 |
|-------|------|---------|----------|
| `cloudflare-access` | 创 R2 API Token | 新装 R2 / 凭据失效时 | Python 脚本调 CF API 自动生成 token（需 Global API Key） |
| `gbrain-backup` | 脑定时备份 | `cron` 每天 3 AM 跑 | 备份到 R2 + Google Drive 双目的地 |
| `gbrain-recovery` | 从备份恢复脑 | 脑坏 / 换机 / 失忆 | rclone copy + tar -xzf |
| `switch-model-m1-m3` | M1 / M3 模型切换 | 陛下说 "M1" 或 "M3" | 改 `~/.hermes/config.yaml` 的 `model.default` |

## 3. 调用顺序

```
cloudflare-access → gbrain-backup → (cron 跑) → gbrain-recovery → switch-model-m1-m3
              ↓                          ↓                ↓
        创 R2 token              备份脑数据          恢复脑数据
```

**前置：cloudflare-access 必须先跑一次**（拿到 R2 token），否则 gbrain-backup 没目标。
**之后 gbrain-backup 配 cron 每天自动跑**。
**gbrain-recovery 是出问题时用**（脑坏、换机）。
**switch-model-m1-m3 是任何时候陛下说"M1"/"M3"时用**。

## 4. 怎么用 gbrain（前提：本机有脑 / SSH 50.161）

```bash
# 看健康分
cd ~/.hermes/skills/gbrain && bun src/cli.ts doctor

# 查 page（按关键词）
cd ~/.hermes/skills/gbrain && bun src/cli.ts query "GitHub PAT"

# 写 page（自动 embed + extract links）
cd ~/.hermes/skills/gbrain && bun src/cli.ts put <slug> --content "..."

# 拉备份恢复
rclone copy gbrain_r2:huawei-car-raw/gbrain/gbrain-latest.tar.gz /tmp/
tar -xzf /tmp/gbrain-*.tar.gz -C /home/ianlee168/gbrain-data/

# 验
cd ~/.hermes/skills/gbrain && bun src/cli.ts list
```

## 5. hindsight 是什么

**hindsight = 陛下早先的"对话记忆"项目**（独立于 gbrain）。状态：
- 装没装：**本机 50.161 没装**（未配）
- 用途：抓 gbrain 之外的对话历史（Slack/Telegram/X 等）
- 跟 gbrain 的关系：hindsight 是 gbrain 的"上游"数据源（hindsight 抓 → gbrain ingest）

**如果你（bot）被要求"用 hindsight"：**
1. 检查 `~/.hindsight/` 是否存在 → 不存在就是没装
2. 跑 `pip install hindsight` 或 `git clone` hindsight 仓到本地
3. 配 OAuth token（跟 gbrain 一样的私仓 token 路径）
4. 起 daemon / 配 cron

**现在 50.161 没 hindsight**。bot 跑 hindsight 相关命令会报 "no module" 或 "command not found"——这是事实，不是 bug。

## 6. 关键约束（不要越界）

- **脑里数据安全 > 涨分**。删任何东西前先确认 + 留 undo。
- **OAuth 原始 token 不进 agent context**。所有 Google / social API 走 ClawVisor（如果配置）；不配就走本地 OAuth 文件。
- **所有 gbrain 命令必须 `cd ~/.hermes/skills/gbrain && bun src/cli.ts ...`**，**不要**用 `bin/gbrain` 编译版。
- **跨 profile 写文件会被软拦**——陛下让你改哪个 profile，明确说"改 default" 或 "改 webui-hermes"，不要自己挑。
- **陛下铁律：先查证再答**。"现在多少分" = 跑 `doctor`；"备份正常吗" = 跑 `tail` + `rclone lsl`。**不要靠记忆/脑测给数字**。

## 7. bot 怎么停止"傻傻的"

读完这 7 段 + 4 卷 SKILL.md，你**应该会**：
- 听陛下说"M1" → 读 switch-model-m1-m3 改 config
- 听陛下说"备份" → 读 gbrain-backup 看 cron 状态
- 听陛下说"多少分" → 跑 `bun src/cli.ts doctor`
- 听陛下说"恢复" → 读 gbrain-recovery 走 4 步

**你**不会**的事（合理拒答）**：
- "Windows 端跑 gbrain 怎么配" → 答"Windows 端没脑可跑，去 50.161 真机"
- "hindsight 怎么配" → 答"50.161 没装 hindsight，需要 OAuth + pip install"
- "rclone.conf 在哪" → 答"50.161 在 `/home/ianlee168/.config/rclone/rclone.conf`，本机空"

**该问陛下的事**：
- "陛下是想 50.161 上做，还是别的机器？"
- "陛下是想真恢复脑，还是想查脑内容？"
- "hindsight 没装，陛下要先装吗？"

别假设，**先问清楚再行动**。
