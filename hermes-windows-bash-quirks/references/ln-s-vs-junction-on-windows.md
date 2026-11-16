# `ln -s` vs `mklink /J` on Windows: Session Detail

Reproduction recipe and exact transcripts for the "Directory Aliasing
on Windows" SKILL.md section. Read this when a future session hits
the same failure mode and needs to see what was tried and what worked
on 50.110.

## The original failure (50.110, 2026-06-11)

**Setup:**
- MSYS bash (Git Bash) on Windows 10/11
- Non-admin user (`ianlee168`), Developer Mode OFF
- Goal: soft-link 3 Claude Code skills (`xiaohu-video-md`,
  `xiaohu-subtitle-polish`, `xiaohu-video-download`) into
  `~/.hermes/skills/` so the Hermes agent's `read_file` could
  access them.

**Attempt 1: `ln -s` loop:**
```bash
cd /c/Users/<user>/.hermes/skills/ && for s in xiaohu-video-md \
  xiaohu-subtitle-polish xiaohu-video-download; do
  ln -s "/c/Users/<user>/.claude/skills/$s" "$s"
  if [ -L "$s" ]; then
    echo "[OK]   $s -> $(readlink "$s")"
  else
    echo "[FAIL] $s 创建失败"
  fi
done
```

**Output:**
```
[FAIL] xiaohu-video-md 创建失败
[FAIL] xiaohu-subtitle-polish 创建失败
[FAIL] xiaohu-video-download 创建失败
```

**`ls -la` output (the "evidence" that things failed):**
```
drwxr-xr-x 1 <user> <group>   0  6月 11 03:59 xiaohu-subtitle-polish
drwxr-xr-x 1 <user> <group>   0  6月 11 03:59 xiaohu-video-download
drwxr-xr-x 1 <user> <group>   0  6月 11 03:59 xiaohu-video-md
```

No `l` (link) marker. All three showed as `d` (directory). The
loop script reported FAIL on all three.

**But cross-link read worked perfectly:**
```bash
$ head -5 /c/Users/<user>/.hermes/skills/xiaohu-video-md/SKILL.md
---
name: 视频转写
description: "视频转写与翻译工具：抓取字幕/音频转写 → 输出 Markdown 文档..."
---
```

The YAML frontmatter of the real SKILL.md came back through the
"failed" link.

**Diagnosis:** MSYS `[ -L ]` returned false for a working NTFS
reparse point. The `ln -s` actually succeeded (this is **Outcome B**
in the SKILL.md §"The `ln -s` silent failure mode"). The script
was lying, not the filesystem.

## The `cmd //c` quote-eating failure (same session)

Both `cmd //c "wsl -d Ubuntu-24.04 --status"` and
`cmd //c "dir /AL C:\Users\<user>\.hermes\skills"` displayed a
blank cmd.exe prompt and exited without running the command.
Cause: MSYS quote-stripping + Windows backslash escaping combine
destructively when the argument has both `"` and `\`.

**Workaround pattern that works** (the `.bat` file approach
documented in SKILL.md §"`cmd //c "..."` complex-quote eating"):

```bash
cat > /tmp/bridge_xiaohu.bat << 'BATCH_EOF'
@echo off
mklink /J "C:\Users\<user>\.hermes\skills\xiaohu-video-md" "C:\Users\<user>\.claude\skills\xiaohu-video-md"
mklink /J "C:\Users\<user>\.hermes\skills\xiaohu-subtitle-polish" "C:\Users\<user>\.claude\skills\xiaohu-subtitle-polish"
mklink /J "C:\Users\<user>\.hermes\skills\xiaohu-video-download" "C:\Users\<user>\.claude\skills\xiaohu-video-download"
BATCH_EOF
MSYS_NO_PATHCONV=1 cmd.exe //c "$(cygpath -w /tmp/bridge_xiaohu.bat)"
```

The `MSYS_NO_PATHCONV=1` and `cygpath -w` are both required —
without them the .bat file path itself gets mangled in the
MSYS→cmd translation.

**Not actually executed in this session** because the existing
`ln -s` symlinks were already working. But the pattern is the
verified fallback for next time.

## What if the symlinks hadn't worked? Full recovery path

```bash
# Step 1: rmdir the (working or empty) symlink at the target
cmd //c "rmdir C:\Users\<user>\.hermes\skills\xiaohu-video-md"
# → success (cmd rmdir removes reparse point only, leaves source intact)
# Note: bash `rmdir` would fail with "Directory not empty" because
#       it dereferences the reparse point and sees the source's contents.

# Step 2: mklink /J fresh junction
cmd //c "mklink /J C:\Users\<user>\.hermes\skills\xiaohu-video-md C:\Users\<user>\.claude\skills\xiaohu-video-md"
# → Junction created for C:\Users\<user>\.hermes\skills\xiaohu-video-md

# Step 3: verify with cross-link read (NOT [ -L ])
head -5 /c/Users/<user>/.hermes/skills/xiaohu-video-md/SKILL.md
# → if real content, junction is working
```

## Verification commands that proved the bridge worked (this session)

```bash
# 1. SKILL.md is real and parseable
head -5 /c/Users/<user>/.hermes/skills/xiaohu-video-md/SKILL.md
# → --- (YAML frontmatter)
# → name: 视频转写
# → description: "..."

# 2. The user's modified config.json is reachable through the link
grep output_dir /c/Users/<user>/.hermes/skills/xiaohu-video-md/config.json
# → "output_dir": "D:/Videos/translate",  ← the user's value

# 3. The script directory is reachable
ls /c/Users/<user>/.hermes/skills/xiaohu-video-md/scripts/
# → douyin_download.py  douyin_login.py  transcribe_srt.py  ...

# 4. All 3 skills resolve
for s in xiaohu-video-md xiaohu-subtitle-polish xiaohu-video-download; do
  [ -e "/c/Users/<user>/.hermes/skills/$s/SKILL.md" ] && echo "[OK]   $s"
done
# → [OK]   xiaohu-video-md
# → [OK]   xiaohu-subtitle-polish
# → [OK]   xiaohu-video-download
```

## What's still true (and a hard fact for any future bridged skill)

Even with the symlinks in place, `skill_view` and `skills_list`
do **NOT** show the xiaohu-* skills. This is because Hermes
skill discovery doesn't auto-scan `~/.hermes/skills/` (it uses
a plugin/registry system). The 4 user-authored skills already
in that directory (`cloudflare-access`, `gbrain-backup`,
`gbrain-recovery`, `switch-model-m1-m3`) are **also not** in
`skills_list` — same architectural fact, not specific to new
skills. The full diagnosis and three responses (read on demand
/ plugin registration / direct CLI) live in the
`cross-agent-tool-bridging` skill.
