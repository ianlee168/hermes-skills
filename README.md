# hermes-skills — 多 bot 协作约定

**这个仓由 ianlee168 的多个 bot 共同维护。** 任何 bot 改 skill 前**必须**先读这页。

## 目录归属

| 目录 | 谁管 | 改前必读 |
|------|------|----------|
| `gbrain-recovery/` | 50.161 webui-hermes bot | "零硬编" 原则（不改 IP / 平台 / 绝对路径） |
| `gbrain-backup/` | 50.161 webui-hermes bot | 改 `backup.sh` 前看 `references/cron-setup.md`（如有） |
| `gbrain-ops/` | 50.161 webui-hermes bot | 14 节踩坑清单，本机专属 |
| `cloudflare-access/` | 50.161 webui-hermes bot | R2 token 创脚本，本机 rclone 路径专属 |
| `switch-model-m1-m3/` | 50.110 Windows bot | 改 `config.yaml` 路径需自己适配本机 Hermes 配置 |
| `smart-home/` | 50.1 Unraid bot（NAS 端） | go2rtc / Frigate 配置，Unraid 路径专属 |
| `istoreos-passwall-update/` | 50.110 Windows bot | PassWall 升级流程，路由器专属 |
| `skill-github-mirror/` | 50.110 Windows bot | skill→GitHub 同步流程，所有 bot 适用 |
| `hermes-update-troubleshooting/` | 50.110 Windows bot | Hermes 自更新故障排查（含 ZIP fallback 清构建产物坑） |
| `4-SKILLS-USAGE.md` | **所有人** 共同管 | 通用操作上下文，零硬编 |

## 改 skill 前的 3 步

```bash
# 1. 拉最新
cd /tmp/hermes-skills-check
git pull --rebase

# 2. 检查自己改的文件是否别人也改过
git status

# 3. 改完 push
git add <file>
git commit -m "..."
git push origin main
```

**如果 push 报 "rejected" 或 "conflict"**：
- **不要**用 `git push --force`（会覆盖别人的改动）
- 先 `git pull --rebase` → 解冲突 → `git push`

## 通用约定（**所有 bot 必守**）

1. **零硬编** — 不写具体 IP / OS / 绝对路径到 skill。`/home/ianlee168/` / `50.161` / `C:\Users\` / `192.168.50.1` 都是错的。
2. **gbra* 用源码** — `cd ~/.hermes/skills/gbrain && bun src/cli.ts`，**不要**用 `bin/gbrain` 编译版。
3. **不要 commit 字面 token** — `ghp_xxx` / `sk-xxx` / `R2 secret` 全部用 `<占位符>` 替换。`git diff` 时**自己**看一遍再 push。
4. **不要写 "陛下" 称呼** — 写 "ianlee168" 或 "用户"。
5. **先 dry run 再 push** — 改完跑一遍相关命令验证，再 commit。陛下 4 卷 → 王牌规矩"跑通 2 遍再写进 skill"。

## 谁管什么 — 解释

| 改的事 | 谁改 | 谁审 |
|------|------|------|
| `gbrain-*` 系列 | 50.161 webui-hermes bot | 陛下看 git log |
| `switch-*` | 50.110 Windows bot（如有） | 50.161 不审，直接推 |
| `istoreos-passwall-update/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `skill-github-mirror/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `hermes-update-troubleshooting/*` | 50.110 Windows bot（如有） | 50.161 不审 |
| `smart-home/*` | 50.1 Unraid bot（如有） | 50.161 不审 |
| `4-SKILLS-USAGE.md` | **任何 bot 改都行**，但要看 | 跨 bot 改 → push 前必须 `git pull` 看别人改了什么 |

## 冲突常见场景

**场景：bot A 改了 gbrain-recovery 第 5 行，bot B 也改了第 5 行。**
```
bot A push 完（commit X）
bot B 想 push → rejected
bot B 跑:
  git pull --rebase
  # 解决第 5 行冲突（手动选 a / b / both）
  git add gbrain-recovery/SKILL.md
  git rebase --continue
  git push
```

**场景：bot A 改 gbrain-recovery，bot B 改 switch-model-m1-m3。**
- 无冲突，bot B 直接 push 成功。

## 进阶：分支工作流（如果冲突频繁）

如果冲突太多（>1 周 1 次），可以启用分支工作流：

```bash
# bot 改完 push 到自己的分支
git checkout -b bot-<name>-<feature>
git push origin bot-<name>-<feature>
# 告诉 ianlee168 在 GitHub UI 上开 PR
# ianlee168 或 webui-hermes 合并
```

**现在不用**。先按"约定目录归属 + 手动解冲突"跑。

---

## 新 bot 上岗必读

1. **不要** 直接 push 到 main
2. 先 `git clone https://github.com/ianlee168/hermes-skills.git /tmp/hermes-skills-check`
3. 改自己领域的 skill
4. push 前 `git pull --rebase`
5. push 报错就解冲突再 push

**不要** —— 看到 `git push --force` / `git reset --hard` / 直接 rm 别人文件 / 删别人 commit。
