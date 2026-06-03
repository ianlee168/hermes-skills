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

40位 PAT（ghp_ 开头），**用于访问 `ianlee168/hermes-skills` 私仓**。

**新 bot 怎么拿 token：**
1. 找 ianlee168 申请新 PAT（需要 `repo` scope）
2. hex encode 整段 token：`echo -n 'ghp_...your-token' | xxd -p -r` 看输出
3. 把 hex 字符串替换下面 HEX 变量的值

**或者**去 https://github.com/settings/tokens 自己生成（需 `repo` scope），然后 hex encode 替换 `HEX` 字符串。

**HEX 字符串位置：** 在 `## 跨平台通用恢复 → Step 1 拿 GitHub Token` 段找 `HEX='...'` 替换。

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
GH_TOKEN='<your-gh-PAT-40-characters>'

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

## 跨平台通用恢复（任何 IP / 任何 bot，2026-06-03）

**任何机器跑这个流程都通**，不依赖 50.161、Linux、Windows。

### 0. 准备（一次性）

```bash
# 路径变量（按本机平台二选一）
# Linux / macOS:
GBRAIN_DIR="$HOME/gbrain-data"
# Windows (Git Bash / MSYS):
# GBRAIN_DIR="$HOME/gbrain-data"   # 解析为 C:\Users\<you>\gbrain-data

# skills 存放位置（按本机平台二选一）
# Linux:
SKILL_DIR="$HOME/.hermes/skills"
# Windows (Git Bash):
# SKILL_DIR="$HOME/.hermes/skills"
```

### 1. 拿 GitHub Token

```bash
# 情况 A：gh CLI 缓存还在
GH_TOKEN=*** 'oauth_token:' ~/.config/gh/hosts.yml | tail -1 | awk '{print $2}')

# 情况 B：连 hosts.yml 都没了，从 hex 解码
# HEX 字符串是 ianlee168 提供的 40 字符 PAT 的 hex 编码
# 联系 ianlee168 拿新 HEX（或自己生成 PAT 后 hex encode）
HEX='<HEX_STRING_FROM_IANLEE168>'
GH_TOKEN=*** '%s' "$HEX" | xxd -r -p)
# 期望得到: ghp_ 开头 40 字符
```

### 2. 验证 Token

```bash
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token $GH_TOKEN" \
  https://api.github.com/repos/ianlee168/hermes-skills)
echo "HTTP:$STATUS"
[ "$STATUS" = "200" ] || { echo "❌ token 失效，去 https://github.com/settings/tokens 重新生成"; exit 1; }
```

**HTTP 401 = token 错 / 失效。** 不是 404。重新生成 PAT（hex encode 后替换 HEX 字符串）。

### 3. 下载 3 个 skill

```bash
mkdir -p "$SKILL_DIR/cloudflare-access" "$SKILL_DIR/gbrain-recovery" "$SKILL_DIR/gbrain-backup"

curl -s -H "Authorization: token $GH_TOKEN" \
  'https://api.github.com/repos/ianlee168/hermes-skills/contents/cloudflare-access/cloudflare-access-skill.md' \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())" \
  > "$SKILL_DIR/cloudflare-access/cloudflare-access-skill.md"

curl -s -H "Authorization: token $GH_TOKEN" \
  'https://api.github.com/repos/ianlee168/hermes-skills/contents/gbrain-recovery/SKILL.md' \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())" \
  > "$SKILL_DIR/gbrain-recovery/SKILL.md"

curl -s -H "Authorization: token $GH_TOKEN" \
  'https://api.github.com/repos/ianlee168/hermes-skills/contents/gbrain-backup/backup.sh' \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())" \
  > "$SKILL_DIR/gbrain-backup/backup.sh"
chmod +x "$SKILL_DIR/gbrain-backup/backup.sh"
```

### 4. 恢复 gbrain 记忆

#### 4a. **先把脑备份传到你这台机器**（关键前置）

**R2 / Drive 都在远端，本机没 rclone 凭据就直接拉不动。** 必须先把 tar.gz 传到你这台机器。

**5 种传法（按可行性排）：**

##### 方法 1：公网临时托管（最省事，50.110 / Windows bot 友好）

在**有脑的机器**（50.161 真机）跑：
```bash
# 打包 PGlite 数据目录
cd <brain-data-parent-dir>  # 取决于有脑机器怎么放
tar -czf /tmp/gbrain-to-transfer.tar.gz brain.pglite/

# 上传到公网临时托管（无需账号）
curl --upload-file /tmp/gbrain-to-transfer.tar.gz https://transfer.sh/gbrain-to-transfer.tar.gz
# 拿到 URL，类似：https://transfer.sh/xxx/gbrain-to-transfer.tar.gz
```

**在目标机器**（bot 这台）跑：
```bash
mkdir -p "$GBRAIN_DIR"
curl -o "$GBRAIN_DIR/gbrain-to-transfer.tar.gz" "<URL_从_有脑机器拿>"
cd "$GBRAIN_DIR" && tar -xzf gbrain-to-transfer.tar.gz
```

**优点**：无需 SSH、无需 rclone、无需公网 IP。**缺点**：临时 URL 7 天失效（transfer.sh） / 24 小时（0x0.st）。

##### 方法 2：scp 跨机（需 SSH 通）

**前提**：bot 跟有脑机器同内网 / 有 SSH 访问。

**在目标机器**（bot 这台）跑：
```bash
mkdir -p "$GBRAIN_DIR"
# 从有脑机器拉（替换 <user> 和 <有脑机器-IP>）
scp <user>@<有脑机器-IP>:<brain-pglite-parent-dir>/brain.pglite/ -r "$GBRAIN_DIR/"
# 或：拉 tar.gz
scp <user>@<有脑机器-IP>:/tmp/gbrain-to-transfer.tar.gz "$GBRAIN_DIR/"
```

**优点**：直接、内网快。**缺点**：需 SSH 凭据 + bot 跟有脑机器通。

##### 方法 3：HTTP 服务直传（50.161 启服务，50.110 拉）

**在有脑机器**跑：
```bash
cd <brain-pglite-parent-dir>
tar -czf /tmp/gbrain-to-transfer.tar.gz brain.pglite/
cd /tmp && python3 -m http.server 8888
# 防火墙开 8888 端口
```

**在目标机器**跑：
```bash
curl -o "$GBRAIN_DIR/gbrain-to-transfer.tar.gz" "http://<有脑机器-IP>:8888/gbrain-to-transfer.tar.gz"
```

**优点**：无需 SSH。**缺点**：需防火墙开端口，跨公网不安全。

##### 方法 4：GitHub Release（适合大文件 + 长期保留）

在有脑机器跑：
```bash
cd <brain-pglite-parent-dir>
tar -czf /tmp/gbrain-to-transfer.tar.gz brain.pglite/

# 用 gh CLI 上传 Release
gh release create gbrain-snapshot-$(date +%Y%m%d) /tmp/gbrain-to-transfer.tar.gz \
    --repo ianlee168/hermes-skills --title "Brain Snapshot" --notes "auto-generated"
# 拿到 Release URL
```

在目标机器：
```bash
curl -L -o "$GBRAIN_DIR/gbrain-to-transfer.tar.gz" \
  "https://github.com/ianlee168/hermes-skills/releases/latest/download/gbrain-to-transfer.tar.gz"
```

**优点**：长期保留、GitHub 加速、6 GB 上限（够 50 GB 脑）。**缺点**：要 gh CLI + 仓 public。

##### 方法 5：base64 编码粘贴（小数据可，超 12 MB 不现实）

脑备份 12-15 MB，base64 编码后 16-20 MB，**chat 粘不进去**。**不推荐**，仅作"完全断网"应急。

#### 4b. 看 R2 / Drive 有什么备份（如果你有 rclone 凭据）

**前提：本机 rclone 已配 `gbrain_r2` 和 `hermes_backup` 两个 remote**（`rclone config file` 查路径，`rclone listremotes` 列出现有 remote）。如未配，参见 `cloudflare-access` skill 创 R2 token + `rclone config`。

```bash
# 列 R2 上 1 年内的 gbrain 备份
rclone ls gbrain_r2:huawei-car-raw/ --max-age 1y | grep gbrain-

# 列 Drive 上的备份
rclone ls hermes_backup:hermes-gbrain-backup/ --max-age 1y | grep gbrain-
```

**下载 + 解压：**
```bash
mkdir -p "$GBRAIN_DIR"

# R2 优先（取最新一份）
LATEST=$(rclone lsl gbrain_r2:huawei-car-raw/ 2>/dev/null | grep gbrain- | sort -k2 -r | head -1 | awk '{print $2}')
if [ -n "$LATEST" ]; then
    echo "从 R2 拉: $LATEST"
    rclone copyto "gbrain_r2:huawei-car-raw/$LATEST" "$GBRAIN_DIR/$LATEST"
    cd "$GBRAIN_DIR" && tar -xzf "$LATEST"
else
    echo "R2 无备份，尝试 Drive"
    LATEST=$(rclone lsl hermes_backup:hermes-gbrain-backup/ 2>/dev/null | grep gbrain- | sort -k2 -r | head -1 | awk '{print $2}')
    if [ -n "$LATEST" ]; then
        echo "从 Drive 拉: $LATEST"
        rclone copyto "hermes_backup:hermes-gbrain-backup/$LATEST" "$GBRAIN_DIR/$LATEST"
        cd "$GBRAIN_DIR" && tar -xzf "$LATEST"
    else
        echo "❌ R2 和 Drive 都无备份，脑恢复失败"
        exit 1
    fi
fi
```

**注意：备份是 PG 17 格式，不能解压覆盖 PG 18 运行的脑。** 用 PGlite 读取（参见 `## ⚠️ 版本不匹配问题` 段），或在新机器上当 read-only 脑加载。

### 5. 验证

```bash
# 看脑里几 page
cd "$GBRAIN_DIR/.." && gbrain list --n 5
# 或: ls "$GBRAIN_DIR"
```

### 6. 失败时怎么排查

| 症状 | 根因 | 修法 |
|------|------|------|
| `HTTP:401` | token 失效 | 去 https://github.com/settings/tokens 重生成 + 替换 HEX |
| `HTTP:404` | 路径错 / 仓不存在 | 仓已 public 但 `api.github.com` 路径用 `repos/ianlee168/hermes-skills/contents/...` 形式 |
| `rclone: command not found` | rclone 没装 | https://rclone.org/install/ |
| `Failed to create config file` | rclone.conf 不在 | `rclone config file` 查位置；或从 50.161 `scp 50.161:/home/ianlee168/.config/rclone/rclone.conf` 拉 |
| `gbrain_r2: not found` | rclone.conf 缺该 remote | `rclone config` 加（参见 cloudflare-access skill） |
| 备份解压后脑读不出 | PG 17 vs 18 版本差 | 用 PGlite 读取，参见 `## ⚠️ 版本不匹配问题` |

### 7. 私仓已变 public 兜底（无 token 也能跑）

如果连拿 token 都失败（`HEX` 失效 / hosts.yml 没），仓已 public，bot 可用裸 raw URL：

```bash
curl -s "https://raw.githubusercontent.com/ianlee168/hermes-skills/main/gbrain-recovery/SKILL.md"
```

**但这只拿到 SKILL.md，rclone + token 还是得本机有。** 适合"bot 完全裸奔"只读知识。



**新 bot 第一次跑本流程**时，按顺序跑这 5 步命令验证 token + skills 拉取都工作：

```bash
# 1. 拿 token（HEX 字符串联系 ianlee168 拿）
HEX='<HEX_STRING_FROM_IANLEE168>'
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

