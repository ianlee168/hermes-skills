# Health Score Playbook — 实战数据

> 本文件是 gbrain-ops SKILL.md 第 8 段的详细数据。简短结论看 SKILL.md。

## 起点 vs 终点（2026-06-02 单次会话）

| 指标 | 起点 | 终点 | 涨分 |
|------|------|------|------|
| Brain score | 55/100 | **87/100** | +32 |
| embed | 35/35 | 35/35 | 0 |
| links | 1/25 (5.6%) | 25/25 (92.6%) | +24 |
| timeline | 0/15 | 3/15 | +3 |
| orphans | 2/15 | 14/15 | +12 |
| dead-links | 10/10 | 10/10 | 0 |
| graph_signals_coverage | 2.3% | 92.6% | +90.3pp |
| multi_source_drift | 0 | 0 | 0 |

## 操作时间线

| 步骤 | 耗时 | 命令 |
|------|------|------|
| 1. export 18 page 拿最新内容 | ~5s | `bun src/cli.ts export --dir /tmp/gbrain-export` |
| 2. 写 8 个新 page + 1 个 projects/knowledge-base-index | ~5min | 手动写 + python 改 link 形式 |
| 3. python 脚本把所有 link 改成相对路径 | ~2s | 跨 dir 加 `../`，同 dir 留简写 |
| 4. mkdir + git init brain-default 仓 | ~1s | `mkdir -p /home/ianlee168/brain-default && git init` |
| 5. cp 全部 page 进去 + git commit | ~2s | |
| 6. SQL 直连 PGlite 改 default.local_path | ~5s | bun 脚本（见 SKILL.md 第 10 条） |
| 7. sync 9 page 进 default source | ~273s | `bun src/cli.ts sync --source default` |
| 8. extract all 抽 75 link | ~30s | `bun src/cli.ts extract all --source fs --dir /home/ianlee168/brain-default` |
| 9. 5 个 page 加 timeline entry | ~2min | `### YYYY-MM-DD — 标题` 格式 |
| 10. 重新 sync + 抽 timeline | ~180s | |
| **总计** | **~13min** | |

## 关键命令合集

```bash
# 1. 导出脑里最新内容（拿 base）
cd ~/.hermes/skills/gbrain && bun src/cli.ts export --dir /tmp/gbrain-export

# 2. 写新 page（直接 write_file）+ 改 link 形式（python 脚本，见 SKILL.md 第 11 条）

# 3. 准备 brain 仓
mkdir -p /home/ianlee168/brain-default
cp -r /home/ianlee168/brain-default-fresh/* /home/ianlee168/brain-default/  # 18 旧 page
cp /tmp/gbrain-export/concepts/*.md /home/ianlee168/brain-default/concepts/  # 新 page
cp /tmp/gbrain-export/projects/*.md /home/ianlee168/brain-default/projects/
cd /home/ianlee168/brain-default && git init -q && git add -A && git commit -m "init"

# 4. 配 default.local_path（关键！见 SKILL.md 第 10 条）
# 5. sync
cd ~/.hermes/skills/gbrain && bun src/cli.ts sync --source default
# 输出："Extracted: N links, M timeline entries" — 注意 M > 0 才是成功

# 6. extract
cd ~/.hermes/skills/gbrain && bun src/cli.ts extract all --source fs --dir /home/ianlee168/brain-default

# 7. 验证
cd ~/.hermes/skills/gbrain && bun src/cli.ts doctor | grep -E 'WARN|score'
```

## 各种失败模式与恢复

### "0 links, 0 timeline entries" 但 dry-run 显示有内容

`extract` 实跑 0，`--dry-run` 显示 75 → 99% 是**源 source 不对**。fs extract 用 `from_source_id = 'default'`，如果 page 在 `exported`/`other` source，JOIN 失败 → 0 created。

修法：把 page 移到 default source，或给 default 配 `local_path` 后 sync 一次。

### dream 报 "requires a local brain directory"

`dream` 的 11 个 phase 中，6 个（lint/backlinks/sync/synthesize/extract/patterns）需要 local_path。default 没配就全 skip。修法同 SKILL.md 第 10 条。

### PGlite 脚本 timeout 但 lock 残留

`rm /home/ianlee168/.gbrain/brain.pglite/.gbrain-lock/lock`，先 `ps -p <pid>` 确认进程不在了。

### sync 报 "Not a git repository"

目标 local_path 不是 git 仓 → `cd <local_path> && git init && git add -A && git commit`。

## 教训 / 注意事项

1. **不要先 `gbrain sources add <id>`** — 会触发 multi_source_drift，最后算分反而掉。直接改 default.local_path。
2. **小脑 < 30 page** 把目标定 75-85，别死磕 95+。
3. **timeline 必须用 `### YYYY-MM-DD` 或 `**YYYY-MM-DD** | Source — Summary`**，其它格式全不识别。
4. **DIR_PATTERN 白名单外的 dir** 下的 page（ops/credentials/skills/environment/smart-home/user）永远 orphan，要么删，要么改 dir 名到白名单内。
5. **edit 完 page 跑 `bun src/cli.ts sync --source default`**，sync 会自动重抽 link 和 timeline，不用手动跑 extract。
6. **要 embed 重跑** 用 `bun src/cli.ts embed --all`，但要 ollama 先起来（`ps aux | grep ollama`）。

## 关联 skill

- `switch-model-m1-m3` — 跟 M1/M3 模型切换有关（用到 m1 时 ollama 跑 embed）
- `software-development/writing-plans` — 18+ page 修改前先写 plan
