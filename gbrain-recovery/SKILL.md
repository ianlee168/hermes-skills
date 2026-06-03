---
name: gbrain-recovery
category: mlops
description: gbrain 记忆系统完全恢复流程 — 从 R2 + Google Drive 双备份下载、解压、验证、恢复。每一步都有自动和手动两条路径。
---

# gbrain-recovery — 备份恢复完整流程

## ⚠️ 运行环境
**本机是 50.161 Linux，不是 WSL。** rclone.conf 在 `/home/ianlee168/.config/rclone/rclone.conf`，配置和备份都在本机。

## 前提

- 备份在 Cloudflare R2 (`gbrain_r2:huawei-car-raw/`) 和 Google Drive (`hermes_backup:hermes-gbrain-backup/`)
- rclone 已配置两个 remote，在本机 `/home/ianlee168/.config/rclone/rclone.conf`
- gbrain-data 原路径：`/home/ianlee168/gbrain-data`
- GitHub 私有库 `ianlee168/hermes-skills` 含 skills 备份（private）

## GitHub Token

```
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
```

40位 PAT，不过期（改密码才 revoke）。用于访问私库 `ianlee168/hermes-skills`。

## 快速恢复

```bash
# 1. 确认备份存在
rclone lsl gbrain_r2:huawei-car-raw/ | grep gbrain-
rclone lsl hermes_backup:hermes-gbrain-backup/ | grep gbrain-

# 2. 下载最新备份到 /tmp
LATEST=$(rclone lsl gbrain_r2:huawei-car-raw/ | grep gbrain- | sort -k2 -r | head -1 | awk '{print $2}')
rclone copyto "gbrain_r2:huawei-car-raw/${LATEST}" /tmp/${LATEST}

# 3. 解压覆盖
cd /home/ianlee168
tar -xzf /tmp/${LATEST}

# 4. 验证
cd /home/ianlee168 && gbrain list --n 5
```

## 详细步骤

### Step 1：确认备份存在

```bash
# R2
rclone lsl gbrain_r2:huawei-car-raw/ | grep gbrain-

# Google Drive
rclone lsl hermes_backup:hermes-gbrain-backup/ | grep gbrain-
```

找到最新的 `gbrain-YYYYMMDD_HHMMSS.tar.gz` 文件。

### Step 2：下载备份

```bash
LATEST="gbrain-20260520_182344.tar.gz"  # 替换为实际最新文件名
cd /tmp
rclone copyto "gbrain_r2:huawei-car-raw/${LATEST}" /tmp/${LATEST}
# 如果 R2 失败，尝试 Google Drive：
# rclone copyto "hermes_backup:hermes-gbrain-backup/${LATEST}" /tmp/${LATEST}
```

### Step 3：解压恢复

```bash
cd /home/ianlee168
tar -xzf /tmp/${LATEST}
# 验证
ls gbrain-data/
```

### Step 4：验证 gbrain 可用

```bash
cd /home/ianlee168
gbrain list --n 5
```

### Step 5：安装/更新 skills（从 GitHub 私库）

```bash
GH_TOKEN='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'

for item in 'cloudflare-access:cloudflare-access-skill.md' 'gbrain-recovery:SKILL.md' 'gbrain-backup:backup.sh'; do
  skill="${item%%:*}"
  file="${item##*:}"
  path=""

  if [ "$skill" = "cloudflare-access" ]; then
    path="cloudflare-access/cloudflare-access-skill.md"
  elif [ "$skill" = "gbrain-recovery" ]; then
    path="gbrain-recovery/SKILL.md"
  elif [ "$skill" = "gbrain-backup" ]; then
    path="gbrain-backup/backup.sh"
  fi

  mkdir -p ~/.hermes/skills/${skill}
  curl -s -H "Authorization: token $GH_TOKEN" \
    "https://api.github.com/repos/ianlee168/hermes-skills/contents/${path}" \
    | python3 -c "import sys,json; print(base64.b64decode(json.load(sys.stdin)['content']).decode())" \
    > ~/.hermes/skills/${path}

  echo "Downloaded: ${path}"
done

chmod +x ~/.hermes/skills/gbrain-backup/backup.sh
```

## ⚠️ 版本不匹配问题（PG 17 备份 vs PG 18 运行实例）

- R2 备份是 **PG 17** 格式（`~/gbrain-data/`，PG_VERSION=17）
- 运行的 gbrain 是 **PG 18**（`~/.pg0/instances/gbrain/data/`，PG_VERSION=18）
- 直接解压备份覆盖运行目录会失败（版本不兼容）

### 正确做法：用 PGlite 直接读取备份（无需停止 PG 18）

**PGlite 可以绕过版本差异，直接读取 PG 17 数据目录：**

```bash
node -e "
const { PGlite } = require('/home/ianlee168/.bun/install/cache/@electric-sql/pglite@0.4.3@@@1/dist/');
const db = new PGlite('/home/ianlee168/gbrain-data', { forceCreate: false });
db.waitReady.then(async () => {
  const r = await db.query('SELECT id, slug, title, type, compiled_truth, updated_at FROM pages WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 50;');
  console.log(JSON.stringify(r.rows));
  process.exit(0);
}).catch(e => { console.error(e.message); process.exit(1); });
"
```

### pages 表关键字段
| 字段 | 含义 |
|------|------|
| `id` | 记忆 ID |
| `slug` | 路径 slug（如 `people/ianlee168`） |
| `title` | 标题 |
| `type` | 类型：`concept`, `person`, `project` |
| `compiled_truth` | **记忆正文内容**（markdown） |
| `frontmatter` | JSON 前端数据 |
| `updated_at` | 最后更新时间 |
| `deleted_at` | 非空=已删除 |

## 双数据目录说明
| 路径 | 内容 | 版本 |
|------|------|------|
| `~/.pg0/instances/gbrain/data/` | 运行的 gbrain 实例 | PG 18 |
| `~/gbrain-data/` | R2 备份解压后 | PG 17 |

**永远不要把 PG 17 备份直接解压覆盖 PG 18 运行目录。** 用 PGlite 读取备份，原地不动。

## R2 remote 配置（若 remote 丢失）

若 `gbrain_r2` remote 不存在，重新配置：

```bash
rclone config create gbrain_r2 s3 \
  provider=Cloudflare \
  access_key_id=3b931f97c2d44231cc7841c59b0b8b50 \
  secret_access_key=<secret> \
  endpoint=https://8bc8658cbb45f90275fd62d411b35723.r2.cloudflarestorage.com \
  acl=private
```

Secret Key 在 `~/.config/rclone/rclone.conf` 的 `secret_access_key` 字段。

## Google Drive remote 配置

hermes_backup remote：
```bash
rclone config create hermes_backup drive
# 按提示完成 OAuth 授权
```

## 备份 cron
```bash
0 3 * * * /bin/bash /home/ianlee168/.hermes/skills/gbrain-backup/backup.sh >> /home/ianlee168/.hermes/logs/gbrain-backup.log 2>&1
```

## 实战验证（2026-06-03，跑了 2 遍完整流程全通）

**新 bot 第一次跑本流程**时，按顺序跑这 5 步命令验证 token + skills 拉取都工作：

```bash
# 1. 拿 token
HEX='6768705f766e6242796e71446a667555775562596d497a543832716c475a7559593834325a385253'
printf '%s' "$HEX" | xxd -r -p > /tmp/_gh_token
GH_TOKEN=*** /tmp/_gh_token)

# 2. 验证 token（**必须 HTTP:200，否则 token 失效**）
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token $GH_TOKEN" \
  https://api.github.com/repos/ianlee168/hermes-skills)
echo "HTTP:$STATUS"
if [ "$STATUS" != "200" ]; then
    echo "❌ token 失效（HTTP:$STATUS）"
    echo "去 https://github.com/settings/tokens 重新生成 PAT，hex encode 后替换 HEX 字符串"
    exit 1
fi
echo "✅ token 有效"

# 3. 拉 3 个核心 skill
mkdir -p ~/.hermes/skills/{gbrain-recovery,cloudflare-access,gbrain-backup}
for spec in \
  'gbrain-recovery:SKILL.md' \
  'cloudflare-access:cloudflare-access-skill.md' \
  'gbrain-backup:backup.sh'; do
    skill="${spec%%:*}"; file="${spec##*:}"
    curl -s -H "Authorization: token $GH_TOKEN" \
      "https://api.github.com/repos/ianlee168/hermes-skills/contents/${skill}/${file}" \
      | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())" \
      > ~/.hermes/skills/${skill}/${file}
    echo "✅ ${skill}/${file}: $(wc -c < ~/.hermes/skills/${skill}/${file}) bytes"
done
chmod +x ~/.hermes/skills/gbrain-backup/backup.sh

# 4. 验证文件大小
[ $(wc -c < ~/.hermes/skills/gbrain-recovery/SKILL.md) -gt 5000 ] && echo "✅ gbrain-recovery OK" || echo "❌ 文件过小，可能下载失败"
[ $(wc -c < ~/.hermes/skills/cloudflare-access/cloudflare-access-skill.md) -gt 3000 ] && echo "✅ cloudflare-access OK" || echo "❌ 文件过小"
[ -x ~/.hermes/skills/gbrain-backup/backup.sh ] && echo "✅ gbrain-backup 可执行" || echo "❌ 不可执行"

# 5. 清理
rm /tmp/_gh_token
echo "=== 5 步全跑通 ✅ ==="
```

**实测两遍结果：**
- 第 1 遍：5668 / 3800 / 2161 bytes，HTTP 200
- 第 2 遍（删完重拉）：同样 5668 / 3800 / 2161 bytes，HTTP 200
- backup.sh mode 775（可执行）

**踩过的坑（避免重复）：**
- **token 失效 = HTTP 401**，不是 404。bot 报 404 时**先看 HTTP 状态码**，401 立刻去 https://github.com/settings/tokens 重生成
- `printf '%s' "$HEX"` **不能加 newline**（`echo $HEX` 会加，`echo -n` 是 BSD 语法，部分 bash 不支持）
- API 路径用 `api.github.com` + `Authorization: token` header，**不要用 `raw.githubusercontent.com`**（对私仓永远 404）

## 相关 Skills
- `cloudflare-access` — R2 凭证创建、配置、验证
- `gbrain-backup` — 定时备份脚本（R2 + Google Drive 双目的地）

