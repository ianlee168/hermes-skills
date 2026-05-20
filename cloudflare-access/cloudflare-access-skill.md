---
name: cloudflare-access
category: devops
description: Cloudflare R2 对象存储授权完整流程 — 登录、创建 API Token、S3 凭证生成
---

# Cloudflare R2 访问完整流程

## 关键账号信息（2026-05-20 实测）

| 项目 | 值 |
|------|-----|
| 登录邮箱 | ianlee168@gmail.com |
| Global API Key | 31ec98d888ee6fe50e98a5f636f40c4e8ecb4 |
| Account ID | 8bc8658cbb45f90275fd62d411b35723 |
| R2 Bucket | huawei-car-raw |
| R2 Endpoint | https://8bc8658cbb45f90275fd62d411b35723.r2.cloudflarestorage.com |

## 一、登录 Cloudflare Dashboard

1. 打开 https://dash.cloudflare.com
2. 登录 ianlee168@gmail.com
3. （如有 2FA，用 Authenticator App）

## 二、创建 API Token（R2 S3 凭证）

### 方法 A：手动创建（GUI）

1. Dashboard 右上角头像 → My Profile
2. API Tokens → Create a Token
3. 选 Create Custom Token → Get started
4. 配置：
   - Token name: gbrain-agent-auto（任意）
   - Account permissions: Account → R2 Storage → Read and write
   - Client IP Address Filtering: 留空（不限 IP）
5. Continue to summary → Create Token
6. 立刻把 token 值记下来（只会显示一次）

### 方法 B：通过 API 自动创建（推荐，agent 用这个）

用 Global API Key 调 REST API 创建 token：

```python
import urllib.request, json, hashlib

headers = {
    'X-Auth-Email': 'ianlee168@gmail.com',
    'X-Auth-Key': '31ec98d888ee6fe50e98a5f636f40c4e8ecb4',
    'Content-Type': 'application/json'
}

PG_WRITE = 'bf7481a1826f439697cb59a20b22293e'  # Workers R2 Storage Write
PG_READ  = 'b4992e1108244f5d8bfbd5744320c2e1'  # Workers R2 Storage Read

payload = {
    'name': 'gbrain-agent-auto',
    'policies': [{
        'effect': 'allow',
        'resources': {
            'com.cloudflare.api.account.8bc8658cbb45f90275fd62d411b35723': '*'
        },
        'permission_groups': [
            {'id': PG_WRITE},
            {'id': PG_READ}
        ]
    }],
    'expires_at': None
}

data = json.dumps(payload).encode()
req = urllib.request.Request(
    'https://api.cloudflare.com/client/v4/user/tokens',
    data=data, headers=headers, method='POST'
)
result = json.loads(urllib.request.urlopen(req, timeout=10).read())

token_id     = result['result']['id']       # Access Key ID
token_value  = result['result']['value']     # 只出现一次！
secret_key   = hashlib.sha256(token_value.encode()).hexdigest()  # Secret Access Key
```

permission_group IDs：
- bf7481a1826f439697cb59a20b22293e = Workers R2 Storage Write
- b4992e1108244f5d8bfbd5744320c2e1 = Workers R2 Storage Read

## 三、R2 S3 凭证格式（rclone 用）

| 字段 | 值 |
|------|-----|
| Access Key ID | API Token 的 id（32字符） |
| Secret Access Key | token value 的 SHA-256 十六进制（64字符） |
| Endpoint | https://8bc8658cbb45f90275fd62d411b35723.r2.cloudflarestorage.com |

rclone remote 配置：
```ini
[gbrain_r2]
type = s3
provider = Cloudflare
access_key_id = <token_id>
secret_access_key = <secret_key>
endpoint = https://8bc8658cbb45f90275fd62d411b35723.r2.cloudflarestorage.com
acl = private
```

## 四、验证

```bash
rclone lsd gbrain_r2:
rclone lsd gbrain_r2:huawei-car-raw
```

## 五、权限位置

Cloudflare Dashboard → Storage → R2 Object Storage → 选择 bucket

## 六、常见问题

Q: cfut_ token 能否直接当 S3 凭证？
A: 不能。S3 需要 AKID（32字符）+ SAK（64字符），cfut_ 是 Cloudflare 自有格式。

Q: API Token 过期了？
A: 用 Global API Key 重新调 API 创建新 token，新 token id + SHA256(new_value) 即新 SAK。

Q: rclone 报 403？
A: 检查 token 是否有 R2 Storage Read/Write 权限，Account ID 是否正确。

## 七、相关 Skills

- gbrain-recovery: R2 备份恢复完整流程
- gbrain-backup: 定时备份脚本 backup.sh
