---
name: cold-start-windows
description: gbrain 冷启动 — Windows bot 适配版。8 phase 全跑对空脑 + 没 Google/X 生态的 Windows 机器不适用。本 skill 给出最小可执行 4 步：从 Desktop / OneDrive 散件 import markdown，跳过 6 phase 不适用项，零 OAuth。
---

# gbrain 冷启动 — Windows 适配版

**目标读者：** 刚装 gbrain、首次启动、上下文空白的 Windows bot。

**公网仓对应 skill：** `garrytan/gbrain/skills/cold-start/SKILL.md`（8 phase 完整版）。**那个版本对 ianlee168 的 Windows 机器不适用**——它假设有 Google Workspace / ClawVisor / ChatGPT 导出 / X 档案 / 纪要转录，本机全没有。本 skill 是 Windows 适配。

## 适配原则

- **冷启动 = 起步 5+ pages**，不是把脑填满
- **没有的 phase 标 done-skipped**，不要去配 ClawVisor / 导 OAuth
- **唯一数据源是本机文件系统**（Desktop / Documents / OneDrive / Downloads）

## 执行步骤（4 步，全程无 OAuth）

### Step 1 — 体检 + 列脑

```bash
cd <gbrain 安装目录>
gbrain doctor --json
gbrain list
```

记录：
- 脑里有几 page（期望 0）
- 引擎是 PGLite 还是 Postgres
- schema 版本
- active pack（gbrain-base 还是 gbrain-base-v2）

### Step 2 — 扫本机 markdown 资源（10 分钟）

按这个顺序搜 5 个位置，每找到一个能 import 的目录就停下：

```bash
for dir in "$USERPROFILE\Desktop" "$USERPROFILE\Documents" "$USERPROFILE\OneDrive\Documents" "$USERPROFILE\Downloads" "$USERPROFILE\Obsidian" "$USERPROFILE\Notes"; do
    if [ -d "$dir" ]; then
        md_count=$(find "$dir" -name "*.md" -not -path "*/node_modules/*" 2>/dev/null | wc -l)
        echo "  $dir → $md_count .md files"
    fi
done
```

**预期结果（ianlee168 的 Windows）：**
- Desktop → 4 个散件 + 1 个 SPEC.md（**5 个起步 page**）
- OneDrive/Documents → 数量未知，扫一下
- 其他 → 大概率空

**不要去扫 Windows 回收站 / 系统目录 / AppData**（会引出大量噪音 .md）。

### Step 3 — import markdown 起步

**Desktop 散件：**
```bash
gbrain import "$USERPROFILE\Desktop" --no-embed --workers 4
gbrain import "$USERPROFILE\Desktop\新建文件夹" --no-embed --workers 4 2>/dev/null
```

**OneDrive（如有 markdown）：**
```bash
# 先 scan 看有哪些文件
gbrain archive-crawler --scan-only --path "$USERPROFILE\OneDrive"
# 给陛下看 manifest，等批准再 full ingest
```

**import 完跑体检：**
```bash
gbrain embed --stale        # 补 embedding（可能要 5-10 分钟）
gbrain doctor
```

**预期分数：** 起步 5-15 page，brain score 40-60/100，**够用**。涨到 85+ 需要 50+ pages，那是长期任务。

### Step 4 — 写一条"已恢复"记录到脑

防止下次冷启动再跑一遍：

```bash
# slug 是 concepts/cold-start-windows-report
# 内容：本机状态、import 了什么、还有哪些 phase 没做
```

模板：

```markdown
---
type: concept
title: Cold Start Windows Report — YYYY-MM-DD
tags: [cold-start, windows, onboarding]
---

# Cold Start Windows Report

## 体检时状态
- 引擎: PGLite
- schema: v112
- pack: gbrain-base-v2
- 起始 page: 0
- 体检分: 75/100

## 执行结果
- Phase 1 (Desktop markdown): 5 pages imported
- Phase 7 (OneDrive): skipped (无 markdown) / N pages imported
- Phase 2-6, 8: skipped (无 Google / X / 导出 / 转录)

## 当前脑
- pages: N
- chunks: N
- embeddings: N
- brain score: N/100

## 待办
- [ ] 等陛下手动导出 ChatGPT/Claude 会话（optional）
- [ ] 等陛下配 ClawVisor 解锁 Google 套件（optional）
- [ ] 继续往脑里加 page 涨分
```

写完跑：
```bash
gbrain put concepts/cold-start-windows-report-YYYY-MM-DD
gbrain embed --stale
gbrain doctor
```

## 跳过的 6 phase（不要去做）

| Phase | 为什么跳过 | 何时启用 |
|-------|-----------|----------|
| 2 — Google Contacts | 陛下没配 ClawVisor，OAuth client = 0 | 陛下说"开始用 ClawVisor" |
| 3 — Google Calendar | 同上 | 同上 |
| 4 — Gmail | 同上 | 同上 |
| 5 — AI 会话导出 | Desktop 没有 conversations.json | 陛下手动 export 后放 Desktop |
| 6 — X/Twitter 档案 | 不用 X | 陛下给 tweets.csv |
| 8 — 纪要转录 | 无转录服务订阅 | 陛下订阅 Circleback 等 |

**绝对不要：**
- 配 ClawVisor / OAuth（陛下没要求）
- 拉公网 gbrain 仓其他 .md（key 风险）
- 删 / 改任何现有 page（冷启动只 import，不破坏）

## 跨平台提醒

- Windows bot 的 `~/.hermes/skills/gbrain/` 在 `C:\Users\ianlee168\.hermes\skills\gbrain\`（或装在哪看 gbrain config）
- 命令入口按系统：Windows 用 `bun src\cli.ts` 或装了 alias 直接 `gbrain`
- 全部 8 phase 完整版参考：https://raw.githubusercontent.com/garrytan/gbrain/main/skills/cold-start/SKILL.md
