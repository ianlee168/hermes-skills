# gbrain-recovery skill

## 关键路径（每次失忆必读）

### PGLite 绕过 bunfs 读取 gbrain-data
```javascript
const { PGlite } = require('/home/ianlee168/.bun/install/cache/@electric-sql/pglite@0.4.3@@@1/dist/');
const db = new PGlite('/home/ianlee168/gbrain-data', { forceCreate: false });
// PGlite 可以读取 gbrain 的 PG 17 数据（USE_FLOAT8_BYVAL=0）
```

### gbrain CLI
```
~/.hermes/skills/gbrain/bin/gbrain list
~/.hermes/skills/gbrain/bin/gbrain get <id>
```

### 新数据库（迁移后）
```
postgres://ianlee168@127.0.0.1:5433/postgres
```

### rclone R2 remote
```
gbrain_r2:huawei-car-raw
```

## R2 S3 凭证生成方法（自动化的关键）

Cloudflare R2 的 S3 凭证可以从 API Token 计算出来，**无需手动创建**：

1. 用 Global API Key 创建 R2 API Token：
```python
import urllib.request, json, hashlib

headers = {
    'X-Auth-Email': 'ianlee168@gmail.com',
    'X-Auth-Key': 'GLOBAL_API_KEY',
    'Content-Type': 'application/json'
}

data = json.dumps({
    'name': 'gbrain-agent-auto',
    'policies': [{
        'effect': 'allow',
        'resources': {'com.cloudflare.api.account.ACCOUNT_ID': '*'},
        'permission_groups': [
            {'id': 'bf7481a1826f439697cb59a20b22293e', 'name': 'Workers R2 Storage Write'},
            {'id': 'b4992e1108244f5d8bfbd5744320c2e1', 'name': 'Workers R2 Storage Read'}
        ]
    }],
    'expires_at': None
}).encode()

req = urllib.request.Request(
    'https://api.cloudflare.com/client/v4/user/tokens',
    data=data, headers=headers
)
r = urllib.request.urlopen(req, timeout=10)
result = json.loads(r.read())
token_id = result['result']['id']       # = Access Key ID
token_value = result['result']['value']  # 用于计算 Secret
secret = hashlib.sha256(token_value.encode()).hexdigest()  # = Secret Access Key
```

2. rclone 配置：
```
[gbrain_r2]
type = s3
provider = Cloudflare
access_key_id = <token_id>
secret_access_key = <sha256(token_value)>
endpoint = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

Account ID: `8bc8658cbb45f90275fd62d411b35723`

## 恢复流程

### 1. 检查备份
```bash
rclone lsl gbrain_r2:huawei-car-raw/ | grep gbrain-
```

### 2. 恢复到 gbrain-data
```bash
# 停止 postgres
pkill -f postgres || true

# 下载备份
rclone copyto gbrain_r2:huawei-car-raw/gbrain-YYYYMMDD_HHMMSS.tar.gz /tmp/gbrain-restore.tar.gz

# 解压覆盖
cd /home/ianlee168
tar -xzf /tmp/gbrain-restore.tar.gz

# 修复权限
sudo chown -R ianlee168:ianlee168 /home/ianlee168/gbrain-data

# 重启
pg_ctl -D /home/ianlee168/.pg0/instances/gbrain/data start
```

### 3. 验证
```bash
cd /home/ianlee168 && ~/.hermes/skills/gbrain/bin/gbrain list
```

## 定时备份 cron
```bash
0 3 * * * /bin/bash /home/ianlee168/.hermes/skills/gbrain-backup/backup.sh >> /home/ianlee168/.hermes/logs/gbrain-backup.log 2>&1
```
