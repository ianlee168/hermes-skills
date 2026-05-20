---
name: gbrain-recovery
category: productivity
description: gbrain 记忆恢复完整流程 — 从 R2 或 Google Drive 备份恢复记忆数据
---

# gbrain 记忆恢复流程

## 重要前提（失忆后必读）

失忆后不要做备份！要先恢复。先读本 skill 恢复记忆，其他 skill（cloudflare-access、gbrain-backup）也在 https://github.com/ianlee168/hermes-skills

## 关键账号信息

- 登录邮箱: ianlee168@gmail.com
- Global API Key: 31ec98d888ee6fe50e98a5f636f40c4e8ecb4
- Account ID: 8bc8658cbb45f90275fd62d411b35723
- R2 Bucket: huawei-car-raw
- R2 Endpoint: https://8bc8658cbb45f90275fd62d411b35723.r2.cloudflarestorage.com

## 恢复步骤

### 第一步：重建 R2 S3 凭证（通过 API 自动创建）

用 Global API Key 调 Cloudflare API 创建 token，然后用 SHA-256 生成 S3 凭证：

```python
import urllib.request, json, hashlib

headers = {
    'X-Auth-Email': 'ianlee168@gmail.com',
    'X-Auth-Key': '31ec98d888ee6fe50e98a5f636f40c4e8ecb4',
    'Content-Type': 'application/json'
}

PG_WRITE = 'bf7481a1826f439697cb59a20b22293e'
PG_READ  = 'b4992e1108244f5d8bfbd5744320c2e1'

payload = {
    'name': 'gbrain-agent-auto',
    'policies': [{
        'effect': 'allow',
        'resources': {
            'com.cloudflare.api.account.8bc8658cbb45f90275fd62d411b35723': '*'
        },
        'permission_groups': [{'id': PG_WRITE}, {'id': PG_READ}]
    }],
    'expires_at': None
}

data = json.dumps(payload).encode()
req = urllib.request.Request(
    'https://api.cloudflare.com/client/v4/user/tokens',
    data=data, headers=headers, method='POST'
)
result = json.loads(urllib.request.urlopen(req, timeout=10).read())

token_id    = result['result']['id']
token_value = result['result']['value']
secret_key  = hashlib.sha256(token_value.encode()).hexdigest()
# token_id    → Access Key ID
# secret_key  → Secret Access Key
```

rclone remote 配置（~/.config/rclone/rclone.conf）:

```ini
[gbrain_r2]
type = s3
provider = Cloudflare
access_key_id = <token_id>
secret_access_key = <secret_key>
endpoint = https://8bc8658cbb45f90275fd62d411b35723.r2.cloudflarestorage.com
acl = private
```

### 第二步：从 R2 下载最新备份

```bash
# 列出可用备份
rclone lsl gbrain_r2:huawei-car-raw/

# 下载最新的备份包
rclone copyto gbrain_r2:huawei-car-raw/gbrain-<日期>.tar.gz /tmp/gbrain-restore.tar.gz

# 解压恢复
tar -xzf /tmp/gbrain-restore.tar.gz -C /home/ianlee168/
```

### 第三步：从 Google Drive 恢复（备选）

```bash
# 如果 R2 不可用，用 Google Drive
rclone lsl hermes_backup:hermes-gbrain-backup/
rclone copyto hermes_backup:hermes-gbrain-backup/gbrain-<日期>.tar.gz /tmp/gbrain-restore.tar.gz
tar -xzf /tmp/gbrain-restore.tar.gz -C /home/ianlee168/
```

### 第四步：验证恢复成功

```bash
cd /home/ianlee168
~/.hermes/skills/gbrain/bin/gbrain list --limit 5
```

## 备份存放位置

- R2: gbrain_r2:huawei-car-raw/gbrain-*.tar.gz
- Google Drive: hermes_backup:hermes-gbrain-backup/gbrain-*.tar.gz

## 相关 Skills

- cloudflare-access: Cloudflare 完整授权流程（R2 S3 凭证生成）
- gbrain-backup: 定时备份脚本 backup.sh（双备份到 R2 + Google Drive）
