# gbrain Wiki Link 语法参考

> 配套 SKILL.md 第 10 条。本文件是完整 cheat sheet + 边界 case。

## 核心规则

gbrain 的 link 解析（src/core/link-extraction.ts + src/commands/extract.ts `resolveSlug`）是**文件系统相对路径**风格，不是 Obsidian 那种 root-relative 风格。

源 page 在 `concepts/gbrain-ops.md`，要 link 到 `concepts/cron-rules`：

```markdown
✅ [[cron-rules]]                       # 同目录，省略 dir
✅ [cron](cron-rules.md)                # markdown 形式
❌ [[concepts/cron-rules]]              # root-relative，gbrain 不认
```

源 page 在 `projects/knowledge-base-index.md`，要 link 到 `concepts/cron-rules`：

```markdown
✅ [[../concepts/cron-rules]]           # 跨目录带 ../
✅ [cron](../concepts/cron-rules.md)
❌ [[concepts/cron-rules]]              # root-relative
```

`path.join('projects', '../concepts/cron-rules')` 自动 normalize 成 `concepts/cron-rules`，不用自己算。

## DIR_PATTERN 白名单

只识别以下 dir 前缀的 link（src/core/link-extraction.ts L46）：

```
people  companies  meetings  concepts  deal  civic
project  projects  source  media  yc
tech  finance  personal  openclaw  entities
```

**白名单外 dir 必然 orphan**（即使 page 存在也无法被 link）：

```
ops/  credentials/  skills/  environment/
smart-home/  user/  test-embed-check/  (根目录无 dir)
```

## 解决白名单外 page 的策略

- **接受它是 orphan**：orphan ratio < 10% 就不扣分（orphans 15/15）
- **加索引 page**：在 `concepts/` 下建新 page "X 索引"，里面用 markdown 普通 link 引用白名单外 page（**extract 不抽**，但人能看）
- **改文件位置**：把 `ops/gbrain-recovery.md` 改名成 `concepts/gbrain-recovery.md`

## 完整形式

```markdown
# 简单 wikilink
[[concepts/cron-rules]]
# 等价于 (跨目录时) [[../concepts/cron-rules]] (从同目录 page)

# 带显示文字
[[concepts/cron-rules|Cron 规则]]

# 限定 source（v0.17+，避免 cross-source 误解析）
[[default:concepts/cron-rules]]
[[exported:concepts/cron-rules]]

# 锚点（去掉）
[[concepts/cron-rules#cleanup-section|Cron 清理]]
```

## 自检脚本（Python 3 stdlib）

写新 page 后跑一遍，看有没有 unresolved link：

```python
import re, os, posixpath

ROOT = '/path/to/brain'
files = []
for root, _, fns in os.walk(ROOT):
    for fn in fns:
        if fn.endswith('.md'):
            files.append(os.path.join(root, fn))

slugs = {f.replace(ROOT + '/', '')[:-3] for f in files}

unresolved = 0
for fp in files:
    d = os.path.dirname(fp).replace(ROOT + '/', '')
    with open(fp) as fh: c = fh.read()
    # 去 code block
    c = re.sub(r'```[\s\S]*?```', '', c)
    for m in re.finditer(r'\[\[([^\]]+)\]\]', c):
        target = m.group(1).split('|', 1)[0].strip()
        if target.startswith(('http', ':', '//')): continue
        if '#' in target:
            target = target.split('#', 1)[0]
        target_no_ext = target[:-3] if target.endswith('.md') else target
        # resolveSlug
        s1 = posixpath.normpath(posixpath.join(d, target_no_ext)).replace('./', '')
        if s1 in slugs: continue
        parts = [p for p in d.split('/') if p]
        ok = False
        for strip in range(1, len(parts) + 1):
            anc = '/'.join(parts[:len(parts) - strip])
            cand = posixpath.normpath(posixpath.join(anc, target_no_ext)).replace('./', '') if anc else target_no_ext
            if cand in slugs:
                ok = True
                break
        if not ok:
            print(f'UNRESOLVED: {fp.replace(ROOT + "/", "")} → [[{target}]]')
            unresolved += 1

print(f'\nunresolved: {unresolved} / {len(files)} files')
```

## 配合 SKILL.md 第 11 条

**关键：** 自检通过只是说 link 在文件层面能解析。**真正写库能不能成功**取决于 extract 模式：

| 模式 | 跨 source 处理 | 适用 |
|------|---------------|------|
| `--source fs --dir <p>` | 写库默认 source_id='default'，non-default source 下 0 row 写入 | 只用 default source 的脑 |
| `--source db --include-frontmatter` | 自动 cross-source resolution（部分 link 被 skip） | 多 source 脑 |

如果是 non-default source（如 `exported`），用 `bun src/cli.ts extract links --source db --include-frontmatter --dry-run --json` 先 dry-run 看能加几个 link，再实跑。
