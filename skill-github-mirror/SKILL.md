---
name: skill-github-mirror
description: 存/改 skill 后同步 GitHub hermes-skills 仓库(脱敏+README 登记)。用户既定习惯。
version: 1.0.0
author: Hermes Agent (50.110)
license: MIT
metadata:
  hermes:
    tags: [GitHub, Skills, Sync, Backup]
    related_skills: [github-repo-management, hermes-agent-skill-authoring]
triggers:
  - "存 skill"
  - "备份 skill 到 github"
  - "skill 同步"
  - "hermes-skills 仓库"
---

# Skill → GitHub 同步(用户既定习惯)

## When to Use

用户(ianlee168)明确要求:**每次创建/修改 skill 后,同步一份到 GitHub 公开仓库 `ianlee168/hermes-skills`**,让其他 bot/agent 也能学习。创建 skill 后立即执行,不用再问。

## 仓库规矩(公开仓库,必守)

1. **脱敏**:密码、token(`ghp_`/`sk-`)、小米账号、密钥路径一律 `<占位符>` 或"见 gbrain"。内网 IP/端口可保留(别的 agent 需要),硬凭证不留。
2. **零硬编**:skill 里不写死具体 IP/OS/绝对路径,用 `<ROUTER_IP>` 这类占位符。
3. **不写"陛下"**:称 "ianlee168" 或 "用户"。
4. **README 归属表**:新目录必须在 `README.md` 的"目录归属"和"谁管什么"两张表各登记一行(50.110 Windows bot → 50.161 不审,直接推)。
5. 改 smart-home/(50.1 bot)等他人目录前先读 README,遵守原归属。

## 流程(已验证,2026-08)

```bash
# 1. 准备:确保 gh 已认证(gh auth status;keyring 登录 ianlee168)
# 2. clone/复用工作区
cd /tmp && rm -rf hermes-skills-github && git clone -q https://github.com/ianlee168/hermes-skills.git hermes-skills-github
cd /tmp/hermes-skills-github

# 3. 拷贝 skill:目录名 = skill 名,文件 = SKILL.md
mkdir -p <skill-name>            # 或 smart-home/<skill-name> 等现有分类
cp <本地SKILL.md路径> <skill-name>/SKILL.md

# 3.5 装到本地(⚠️ 关键一步,GitHub 有 ≠ 本地有)
# 教训(2026-08-27 摄像头断流):skill 在 GitHub 躺了俩月,本地 skills_list 看不到
# → 排查时永远想不起来加载,现场从零瞎试,直到用户提醒"去看 GitHub"。
# 同步后必须复制到本 bot 的 skills 目录,下次才能自动加载:
#   Windows: C:\Users\<user>\AppData\Local\hermes\skills\<category>\<skill-name>\
mkdir -p ~/AppData/Local/hermes/skills/<category>/<skill-name>
cp -r <skill-name> ~/AppData/Local/hermes/skills/<category>/

# 4. 新目录 → 更新 README.md 两张归属表(用 patch 工具,注意保持 CRLF 行尾)

# 5. 若有未提交改动先 stash,再 pull --rebase(防别人已 push)
git stash -u && git pull --rebase && git stash pop

# 6. 配置 git 身份(仓库级,不污染全局;作者取自历史)
git config user.name  "$(git log -1 --format='%an')"
git config user.email "$(git log -1 --format='%ae')"

# 7. 提交前自查(规则#3):grep 硬凭证
git add -A
git diff --cached | grep -inE "q1w2e3|18612798714|R4e3|ghp_|sk-[a-z]|password *=|密码 *=|token *= " && echo "⚠️ 有疑似凭证" || echo "✅ 干净"

# 8. commit + push
git commit -q -m "feat: <说明>"
git push origin main

# 9. 验证远程真的有了
git fetch -q && git log origin/main --oneline -1
gh api repos/ianlee168/hermes-skills/git/trees/main --jq '.tree[].path' | grep <skill-name>
```

## 坑(都踩过)

- **GitHub 有 ≠ 本地有**:skill 只在远程仓库,本 bot 的 skills_list 看不到 → 排查时永远不会被自动加载(2026-08-27 摄像头断流教训:现场从零瞎试直到用户提醒)。同步后按第 3.5 步复制到本地 skills 目录。
- **Windows 上 `/tmp` = `C:/Users/ianle/AppData/Local/Temp`**——write_file 写"用户目录"和 git clone 到 /tmp 是两个地方,文件不会自动合并。要么全部在 /tmp 下操作,要么 copy 过去。
- **git 身份未配置**:`git commit` 报 "Author identity unknown" → 按第 6 步用仓库历史作者配置(ianlee168 <31464826+ianlee168@users.noreply.github.com>),别动全局配置。
- **CRLF/LF**:patch 工具会把目标段换成 LF,git 会显示整文件改动但 diff 内容正确,不必纠结;拷贝新 SKILL.md 用 write_file(LF)即可。
- **有未提交改动时 `git pull --rebase` 直接报错** → 先 stash -u(含 untracked)再 pull。
- **push 被拒**:不要 --force,`git pull --rebase` 解冲突再推。

## 只镜像自己的

- 50.110(臣)的 skill → `istoreos-passwall-update/`(已有)、`switch-model-m1-m3/`、`smart-home/frigate-detection/`(Frigate 域,归 50.1 bot 但臣可补充)。
- 50.161 的 gbrain-* 系列、cloudflare-access 等不动,除非用户明确要求。
- 凭证敏感值永远只在 gbrain(`concepts/net-topology`),公开仓库只放流程。
