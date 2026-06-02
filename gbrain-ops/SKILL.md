---
name: gbrain-ops
description: 踩坑经验 — gbrain 0.38.2.0+ (schema v85+) 在 Linux + Bun 编译 CLI 下的 PGLite 跑法、wiki link 正确语法、extract 模式选择、backup cron 陷阱。**写新 page、加 link、跑 extract/dream 之前必读。** 包含 13 个本地踩过的雷 + 55→87 健康分提升实战路径。
---

# gbrain-ops

本机 (Linux, ~/gbrain) gbrain v0.42.1.0 (schema v85+) 实战踩坑清单。**不**是 gbrain 通用文档，只记本地踩过的雷。

## 1. Bun 编译 CLI 是坏的，源码 + Bun 才是对的

**症状：** `gbrain doctor` / `gbrain list` / `gbrain embed` 任何子命令都报：

```
PGLite failed to initialize its WASM runtime.
  This looks like a Bun vfs issue: `/$$bunfs/root` is read-only on
  your system, so PGLite cannot extract its pglite.data WASM payload.
  ...
  Original error: ENOENT: no such file or directory, open '/$bunfs/root/pglite.data'
```

**根因 + 完整事故时间线：** 见 [`references/bun-pglite-bug.md`](references/bun-pglite-bug.md)

**绕过：** 用源码 + Bun 跑，bunfs 路径是 runtime VFS（writable）。

```bash
# ✅ 工作
cd ~/.hermes/skills/gbrain
bun src/cli.ts doctor
bun src/cli.ts list
bun src/cli.ts embed --all

# ❌ 不工作
~/.hermes/skills/gbrain/bin/gbrain list
gbrain embed --all
```

**Node.js 22 也不行** — gbrain src/ 用了 TypeScript parameter properties (`constructor(public code: ErrorCode, message: string)`)，Node 22 的 strip-only 模式拒绝。

**简化别名**（写入 shell rc）：
```bash
alias gbrain='cd ~/.hermes/skills/gbrain && bun src/cli.ts'
```

## 2. PATH 找不到 gbrain 时的临时救法

非交互 shell（cron、hermes agent 的 terminal tool）不 source `.bashrc`，`gbrain` 命令直接 not found。

```bash
# ❌ command not found
gbrain list

# ✅ 用绝对路径
~/.hermes/skills/gbrain/bin/gbrain list  # ← 还是踩坑 1，会报 bunfs

# ✅ 真正能用
cd ~/.hermes/skills/gbrain && bun src/cli.ts list
```

## 3. embed 慢的实测数据

18 pages / 22 chunks / 265s (~4.4 分钟) — ollama:nomic-embed-text + 本地 PGLite。

跑前先确认 ollama 起来：
```bash
ps aux | grep ollama | grep -v grep
# 没起就
ollama serve &  # 或者 background=true 在 hermes agent 里
```

## 4. PGLite lock 不止 `autopilot.lock`，还有 `.gbrain-lock` 目录

**两个不同的 lock，路径不一样：**

| lock | 路径 | 谁生成 | 残留条件 |
|------|------|--------|----------|
| `autopilot.lock` | `~/.gbrain/autopilot.lock` | autopilot daemon | daemon 异常退出 |
| `.gbrain-lock/lock` | `~/.gbrain/brain.pglite/.gbrain-lock/lock` | PGLite 自身 | INSERT/UPDATE 失败 + 进程崩溃 |

**症状：** 直连 PGLite 的 script 卡住，30s+ 没响应但没有进程在跑。`ps aux | grep bun` 看不到东西，但再跑一次 PGLite script 会超时。

**修法：**
```bash
# 1. 先确认 lock 残留
cat ~/.gbrain/brain.pglite/.gbrain-lock/lock
# → {"pid":12345,"acquired_at":...,"command":"..."}

# 2. 确认 pid 不存在
ps -p 12345   # ← 应该没输出

# 3. 直接删
rm ~/.gbrain/brain.pglite/.gbrain-lock/lock
```

**不要等 5 分钟** —— PGLite 的 `.gbrain-lock` 不像文档说的会自动释放，必须手动清。

**预防：** bun 脚本一定要 `await db.close()` 或用 `try/finally` 包；不要用 `kill -9` 杀 PGLite 进程。

## 5. pg_trgm extension 缺失

直连 PGLite 写 page 时必须显式传 `extensions: { vector, pg_trgm }`：

```js
import { PGlite } from '@electric-sql/pglite';
import { vector } from '@electric-sql/pglite/vector';
import { pg_trgm } from '@electric-sql/pglite/contrib/pg_trgm';

const db = new PGlite('~/.gbrain/brain.pglite', {
  extensions: { vector, pg_trgm },
});
```

漏掉 pg_trgm 会在写 embedding-related schema 时报 `extension "pg_trgm" is not available`。

## 6. backup cron `set -e` 陷阱（已修，2026-06-02）

**完整事故 + 根因分析 + 修法：** 见 [`references/backup-sh-set-e-pitfall.md`](references/backup-sh-set-e-pitfall.md)

核心结论：**`set -e` + pipe-with-while + rclone 是雷区**。清理段必须 `|| true` 包。

`backup.sh` 现在的修复版（清理段）：
```bash
        while read name size; do
            rclone delete "${remote}:${dir}/${name}" 2>/dev/null || true
            log "Deleted old backup: ${name} (${remote})"
        done || true
```

## 7. 写 gbrain page 走直连 PGLite（不推荐 CLI put）

CLI 的 `gbrain put` 走 embed 路径容易 hang（等 ollama，且 PGLite lock 残留），而且踩坑 1 让它完全跑不起来。

**推荐：Node.js / Bun 脚本直连 PGLite INSERT**，最后跑 `bun src/cli.ts embed --all` 单独补 embed。

## 8. 给 source 配 local_path（fs extract 前置条件）

**症状：** `extract all --source fs` 报 0 created / `dream` 的 lint/backlinks/sync/synthesize/extract/patterns 6 个 phase 报 `requires a local brain directory; this brain has no on-disk checkout`。

**根因：** gbrain 0.42 的 fs extract 路径**不传 fromSourceId**，`addLinksBatch` 用 `from_source_id = 'default'` 跟 pages JOIN。page 在非 default source 时全部 ON CONFLICT DO NOTHING → 0 created。

**修法：** SQL 直连 PGLite 改 sources.local_path（CLI 没暴露 `sources update` 子命令）：

```bash
cat > ~/.hermes/skills/gbrain/_update_local_path.ts << 'EOF'
import { PGlite } from '@electric-sql/pglite';
import { vector } from '@electric-sql/pglite/vector';
import { pg_trgm } from '@electric-sql/pglite/contrib/pg_trgm';
const db = await new PGlite('/home/ianlee168/.gbrain/brain.pglite', {
  extensions: { vector, pg_trgm },
});
const r = await db.query(
  `UPDATE sources SET local_path = $1 WHERE id = 'default' RETURNING id, local_path`,
  ['/home/ianlee168/brain-default'],
);
console.log('result:', JSON.stringify(r.rows));
await db.close();
EOF
cd ~/.hermes/skills/gbrain && timeout 30 bun _update_local_path.ts
rm ~/.hermes/skills/gbrain/_update_local_path.ts
```

script 必须放在 gbrain 仓根目录跑（`@electric-sql/pglite` 在那的 node_modules）。超时/卡住就清 `.gbrain-lock`（见第 4 节）。

**别用：** `gbrain sources add <id> --path <p>` 加新 source 再 sync — 会触发 `multi_source_drift`（v0.30.3 之前 `putPage` 误路由），最后算分时反而掉分。

**前置：** 目标 dir 必须是 git 仓（`git init` + 至少一个 commit），否则 sync 报 `Not a git repository`。

## 9. wiki link 必须是相对路径形式

**症状：** 写了 `[[concepts/cron-rules]]` 但 extract 抽不到 link。

**根因：** gbrain 的 `resolveSlug` 是 filesystem-relative，不是 Obsidian 那种 root-relative。从 `concepts/gbrain-ops.md` 看 `[[concepts/cron-rules]]` 解析为 `concepts/concepts/cron-rules`，不在 `allSlugs` 里 → 跳过。

**正确写法：**

```markdown
[[cron-rules]]                              # 同 dir，写文件名（不带 .md）
[[gbrain-ops]]                              # 同 dir
[[../people/ianlee168]]                     # 跨 dir，写相对路径
[[../concepts/cron-rules]]                  # 跨 dir 回到 concepts/
[Name](../concepts/cron-rules.md)           # markdown link 也行
```

**不识别（白名单外）：** `[[ops/x]]` `[[credentials/x]]` `[[skills/x]]` `[[environment/x]]` `[[smart-home/x]]` `[[user/x]]` `[[test-embed-check]]`（根目录无 dir 前缀）— DIR_PATTERN 是 `(people|companies|meetings|concepts|deal|civic|project|projects|source|media|yc|tech|finance|personal|openclaw|entities)`，其它 dir 下的 page **永远不会被人 link 到**，天生 orphan。

**自检脚本（跑前必跑）：**
```python
import re, os, posixpath
slugs = {os.path.join(r,f).replace('./','')[:-3]
         for r,_,fs in os.walk('.') for f in fs if f.endswith('.md')}
def resolve(file_dir, target, all_slugs):
    target_no_ext = target[:-3] if target.endswith('.md') else target
    s1 = posixpath.normpath(posixpath.join(file_dir, target_no_ext)).replace('./','')
    if s1 in all_slugs: return s1
    parts = [p for p in file_dir.split('/') if p]
    for strip in range(1, len(parts)+1):
        anc = '/'.join(parts[:len(parts)-strip])
        cand = posixpath.normpath(posixpath.join(anc, target_no_ext)).replace('./','') if anc else target_no_ext
        if cand in all_slugs: return cand
    return None
# 遍历所有 .md，strip code block 后对每个 [[...]] 调 resolve()
# resolved: 0 的话 link 全部不识别
```

## 10. timeline entry 格式

`extract timeline` 只识别两种格式（`src/commands/extract.ts` line 320+）：

```markdown
# Format 1: bullet
- **2026-06-02** | Source — Summary

# Format 2: header（推荐）
### 2026-06-02 — Title
（紧跟的段落会被当 detail 抓到，下一个 `## ` 或 `### ` 之前）
```

**不识别：** 纯日期段落（无 `### ` 开头）、`## 2026-06-02`（H2 级别）、表格里的日期。

## 11. dream cycle 里 6 个 phase 经常被拒

**症状：** `dream` 跑完只有 1-2 个 phase 实际写入，其它都是 `requires a local brain directory; pass --dir <path> to run filesystem phases`。

**被拒的 6 个 phase：** `lint`, `backlinks`, `sync`, `synthesize`, `extract`, `patterns`

**触发条件：** source 没配 `local_path`（`sources add` 时没带 `--path`）。`source.local_path` 为 null 时这些 phase 直接 skip。

**正确路径：**
1. 先给 source 配 `local_path`（见第 8 节）
2. 跑 `dream` 才会触发全部 phase
3. 或者用 `gbrain doctor --remediation-plan --json` 看缺失哪步

**不要调顶层 `consolidate`** —— 不存在；要走 `dream` 命令或等 autopilot cron。

## 12. child_table_orphans FK 残留

**症状：** doctor 报 `108 orphan row(s) in FK-child tables (content_chunks.page_id=39, page_versions.page_id=9, tags.page_id=58, links.from_page_id=1, links.to_page_id=1)`。

**成因：** 删除 source 时 `ON DELETE CASCADE` 应该级联清子表，但偶尔（特别是跨源 sync、partial import 失败）会有 dangling FK 引用。

**修法：**
```sql
DELETE FROM content_chunks WHERE page_id NOT IN (SELECT id FROM pages);
DELETE FROM page_versions WHERE page_id NOT IN (SELECT id FROM pages);
DELETE FROM tags WHERE page_id NOT IN (SELECT id FROM pages);
DELETE FROM links WHERE from_page_id NOT IN (SELECT id FROM pages);
DELETE FROM links WHERE to_page_id NOT IN (SELECT id FROM pages);
```

走 `bun src/cli.ts doctor` 给的 cleanup SQL 直接跑 PGLite 直连即可。

## 13. 健康分提升实战（55 → 87 实测路径，2026-06-02）

**踩过的弯路**（列出来别重复）：
1. 直接 `extract all` 0 link → 根因 page 之间没 wiki link
2. 加 source 指向导出目录 → `multi_source_drift`，score 跌到 30
3. 调 link 用 root-relative `[[concepts/x]]` → gbrain 不认，extract 0
4. fs extract 0 created → default source 没 `local_path`，fs extract JOIN 失败
5. 直连 PGLite 改 sources.local_path 脚本卡住 → `.gbrain-lock` 残留

**55 → 87 完整路径**（耗时约 30 分钟）：

1. **导出当前脑内容作底版：**
   ```bash
   cd ~/.hermes/skills/gbrain && bun src/cli.ts export --dir /home/ianlee168/brain-default
   ```

2. **在导出目录基础上加新 page**（concepts/projects 白名单 dir）+ 加 wiki link 串图。**关键：link 用相对路径**（见第 9 节）。
   写完跑第 9 节自检脚本。

3. **给 default source 配 `local_path`（见第 8 节）** — SQL 直连 PGLite，timeout 30s。

4. **git init brain dir**（gbrain sync 要求 git 仓）：
   ```bash
   cd /home/ianlee168/brain-default
   git init && git add -A && git -c user.name=x -c user.email=x@x commit -m "init"
   ```

5. **sync + extract（这是真正涨分的步骤）：**
   ```bash
   cd ~/.hermes/skills/gbrain
   bun src/cli.ts sync --source default           # 把 27 page ingest
   bun src/cli.ts extract links --source fs --dir /home/ianlee168/brain-default
   bun src/cli.ts extract timeline --source fs --dir /home/ianlee168/brain-default
   bun src/cli.ts doctor
   ```

6. **加 timeline entry 补 timeline 分**：
   在新 page 末尾加 `### YYYY-MM-DD — 标题` 段（见第 10 节），重新 sync + extract timeline。

**最终分项（实测 87/100）：**
- embed 35/35 ✓
- links 25/25 ✓
- timeline 3/15（6 个 timeline entry，target 覆盖率限制）
- orphans 14/15（剩 1 分是 test-embed-check / user/ian-lee 这种白名单外 dir）
- dead-links 10/10 ✓

**数据量天花板：** 18-25 page 小脑，links/orphans 拿满容易，timeline 难（要 page 内有时间格式）。50+ page 才能稳 90+。page < 30 时目标定 75-85，< 50 page 时定 80-90，别死磕 95+。

---

## 14. 配套工具

- **gbrain doctor** — 看分数（`bun src/cli.ts doctor`）
- **gbrain list** — 列 page
- **gbrain embed --all** — 补 embed
- **bun src/cli.ts** — 上面 3 个命令的真正入口
- **gbrain export** — 导出脑到 .md 目录（用于重建 brain-default）
- **gbrain sync --source <id>** — 真正涨分的入口（必须 source 有 local_path）
- **gbrain extract links/timeline/all --source fs --dir <path>** — 从 fs 抽 link/timeline
- **gbrain dream** — 跑完整 cycle
- **gbrain sources list / status** — 看 source 健康度
- **`~/.gbrain/brain.pglite/.gbrain-lock/lock`** — PGLite 自己的 lock，不是 `autopilot.lock`（见第 4 节）

不踩坑 = 把第 1、4、6、8、9、13 条牢牢记住。
