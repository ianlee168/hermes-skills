---
name: go2rtc-camera
description: go2rtc 流媒体服务器管理 — Xiaomi/米家摄像头 P2P 集成、DID 管理、token 刷新、只读文件系统修复。涵盖 docker-compose 卷挂载、go2rtc API、Xiaomi Cloud 登录状态维护。
triggers:
  - "go2rtc 添加摄像头"
  - "xiaomi camera p2p"
  - "go2rtc i/o timeout"
  - "go2rtc 401 unauthorized"
  - "go2rtc read-only"
  - "摄像头 ip 变了"
  - "摄像头 did 变了"
  - "no frames"
  - "no frames have been received"
  - "摄像头没画面"
  - "没画面"
  - "画面冻结"
  - "快照不变"
  - "5000 断了"
  - "5000 没画面"
  - "frigate 打不开"
---

# go2rtc Camera Streaming

## 快速诊断

> ⚠️ **动手前先读完全文**——尤其"401 风控升级"一节:2026-08-27 起 restart 已不再够用,走弯路会被用户批评"每次都重新瞎搞"。标准顺序:备份 → WebUI 验证码登录 → 确认 streams 节还在 → 查 `/api/streams` bytes。

| 症状 | 第一步 |
|------|--------|
| `no frames have been received` / Frigate 没画面 | 查 `/api/streams`:`{}` → streams 节被清空,从备份恢复;有 producer 但 bytes 不动 → 走 401 风控流程 |
| `i/o timeout` | 确认 DID 是否变了（摄像头 IP 改了 = DID 变了） |
| `401 Unauthorized` | **2026-08-27 起 restart 不再够**(风控升级)→ 走 WebUI 验证码登录流程(见下),不要只 restart |
| `read-only file system` | docker-compose.yml 挂载是 `:ro`，改成 `:rw` |
| Load Devices 无响应 | 检查 NAS 网络能不能访问 `api.io.mi.com` |

---

## ⚠️ 401 凭证过期 = 失联头号原因(2026-08 实战)

**症状**:Frigate 页面没画面,go2rtc 日志每 ~10 秒一条 `401 Unauthorized`,持续数天(实测累计 31,161 次)。
**根因**:小米 P2P 凭证有有效期,过期后 go2rtc 无法向米家云重认证。
**修复**:`docker restart go2rtc` 重启即重新认证,生成全新 P2P 凭证,401 归零。

**已部署看门狗**(Unraid `/boot/custom/scripts/go2rtc-watchdog.sh`,cron 每分钟):
- 检测日志近 2 分钟出现 401 → 自动 `docker restart go2rtc`
- 5 分钟冷却防重复重启;日志 `/boot/custom/scripts/go2rtc-watchdog.log`
- ⚠️ Unraid /boot 是 FAT32 无执行位 → crontab 里必须 `bash xxx.sh` 前缀(chmod +x 无效)
- 持久化:crontab 追加在 `/boot/config/go`(重启自动重挂)

**为什么之前没发现**:监控只盯"画面有没有",没盯日志 401;凭证 3.6 天才出问题,短会话看不出。

### ⚠️ 2026-08-27 风控升级:restart 不再够,必须 WebUI 验证码登录

**症状**:`docker restart go2rtc` 后 401 依旧(8/12 时重启即恢复,这次不行);`i/o timeout` 媒体流读不到;`/api/streams` 里 producer 在但 consumers null、快照字节不变。

**根因**:小米风控升级——令牌过期后 go2rtc 直连登录被拒(401),需**短信验证码**重新认证。

**修复(唯一有效路径)**:
1. 浏览器开 `http://<NAS_IP>:1986` → **add** → 拉到最底 **Xiaomi**
2. 账号框选已有账号 → 密码框填密码 → **login** → 小米要求验证码(captcha + send)
3. 点 **send** → 手机收短信 → 验证码填入 → 确认
4. 登录成功 → go2rtc **自动生成全新 V1 令牌并写回 go2rtc.yaml**(xiaomi 节 userId 行更新)
5. `docker restart go2rtc` → 验证 `/api/streams` 的 `bytes` 增长

**🔴 致命坑(2026-08-27 实测)**:WebUI 登录保存配置时**会重写 go2rtc.yaml,可能把 `streams:` 节整个清空**!
- 症状:登录成功但画面还是没恢复;`/api/streams` 返回 `{}`;yaml 只剩 ~14 行(streams 节空了)
- **改配置前必须先 `cp go2rtc.yaml go2rtc.yaml.bak-$(date +%Y%m%d-%H%M%S)`**(每次都要)
- 修复:从备份把 `streams:` 节加回(append 到 `streams:` 后),再 restart

## 架构

```
go2rtc 容器 (NAS Docker)
  └─ xiaomi://?did=XXXXX  →  米家云 API  →  P2P 链路  →  摄像头
```

- go2rtc 通过 Xiaomi Cloud 获取设备流地址，建立 P2P 直连
- DID（设备 ID）由米家云分配，摄像头 IP 变化 ≠ DID 变化，但 IP 改了且云端未更新时会导致 P2P 失败
- token 存于 `go2rtc.yaml` 的 `xiaomi:` 节，格式为 `userId: V1:encryptedToken`

---

## 典型工作流

### 1. 添加新摄像头（Xiaomi/米家）

```bash
# 确认卷是读写
ssh root@192.168.50.1 "grep 'go2rtc' /mnt/user/appdata/*/docker-compose.yml"
# WebUI: http://<NAS_IP>:1986 → Add → Xiaomi → 登录 → Load Devices → 选择设备
```

### 2. 摄像头 IP 变了（DID 也变了）——完整恢复流程

**典型症状**：之前好好的摄像头突然 `i/o timeout`，但米家 App 能正常看画面。

**原因**：路由器 DHCP 给摄像头分配了新 IP，米家云端 DID 随之更新，但 go2rtc yaml 里还是旧的 DID。

**排查步骤**：
```bash
# 1. 确认摄像头在米家 App 里正常工作（排除硬件/网络层）
# 2. 确认 docker-compose 挂载是 rw（否则 WebUI 保存失败）
ssh root@192.168.50.1 "grep ':ro' /mnt/user/appdata/go2rtc/docker-compose.yml"  # 应无输出
# 3. WebUI 重新登录（清除旧 token）
#    http://192.168.50.1:1986 → Account → Xiaomi → 重新输入账号密码 → Save
# 4. 点 Load Devices，应该能看到"新"设备（DID 已更新）
# 5. 直接查 API 验证新 DID：
ssh root@192.168.50.1 "curl -s http://192.168.50.1:1986/api/streams"
```
**新 DID 在哪里**：WebUI 点 Load Devices 后，列表里会显示 `did=XXXXXXXX`。

**关键修复点**：WebUI 点 Add 按钮后配置**不会自动写入** `go2rtc.yaml`！必须手动写入：

```bash
# 写入新 DID 到 yaml（示例值，需替换）
ssh root@192.168.50.1 "cat > /tmp/cw300_stream.txt << 'EOF'
streams:
  cw300:
    - \"xiaomi://<userId>:cn@<新IP>?did=<新DID>&model=mxiang.camera.moc001&retries=60&timeout=30s\"
EOF
# 合并到现有配置（保留 xiaomi: token 节）
ssh root@192.168.50.1 'python3 -c "
import yaml, sys
with open(\"/mnt/user/appdata/go2rtc/go2rtc.yaml\") as f:
    cfg = yaml.safe_load(f)
with open(\"/tmp/cw300_stream.txt\") as f:
    new = yaml.safe_load(f)
cfg.update(new)
with open(\"/mnt/user/appdata/go2rtc/go2rtc.yaml\", \"w\") as f:
    yaml.dump(cfg, f, default_flow_style=False)
" && docker restart go2rtc'
```

**验证 P2P 建立**：
```bash
ssh root@192.168.50.1 "curl -s http://192.168.50.1:1986/api/streams"
# bytes_recv > 0 且有 video H265 → P2P 已通
```

### 3. token 刷新（401 Unauthorized）

米家密码改了或 token 过期时，需要清除旧 token 重新认证：

```bash
# 备份后清空 xiaomi 节
ssh root@192.168.50.1 "cp /mnt/user/appdata/go2rtc/go2rtc.yaml /mnt/user/appdata/go2rtc/go2rtc.yaml.bak"
ssh root@192.168.50.1 "sed -i '/^xiaomi:/,/^[^ ]/d' /mnt/user/appdata/go2rtc/go2rtc.yaml && docker restart go2rtc"
# 注意：新配置只有 username/password，go2rtc 会重新登录并生成 token
```

### 4. 只读文件系统修复

go2rtc docker-compose 默认挂载为 `:ro`（只读），导致 WebUI 保存配置失败：

```bash
ssh root@192.168.50.1 "sed -i 's/:ro/:rw/' /mnt/user/appdata/go2rtc/docker-compose.yml && cd /mnt/user/appdata/go2rtc && docker compose up -d"
```

**验证**：`docker inspect go2rtc --format '{{json .Mounts}}'` 中 `RW: true`

---

## go2rtc API 常用端点

| 端点 | 用途 |
|------|------|
| `GET /api/streams` | 列出所有流 |
| `GET /api/streams?src=NAME` | 单流详情（含 producer URL） |
| `DELETE /api/streams?src=NAME` | 删除流（需要 prompt 确认） |
| `GET /api/xiaomi` | 列出已存 Xiaomi 账号 |
| `GET /api` | 服务器信息（版本、配置路径） |

---

## P2P 状态验证（推荐方式）

**不要**盯着日志数 minutes，直接查 API：

```bash
ssh root@192.168.50.1 "curl -s http://192.168.50.1:1986/api/streams"
```

**别被快照骗**:latest.jpg 字节数不变可能是**冻结帧缓存**(静态场景或断流),硬验证只有 `/api/streams` 的 `bytes` 持续增长 + producer 有 `remote_addr`(如 `192.168.50.66:26024`)和 `user_agent`(如 `CS2 (mxiang.camera.moc001)`)。

判断标准(API 输出):
- `producers` 为空 / `bytes: 0` → P2P 未建立,超时中
- `bytes` 持续增长(如 54 万字节 + 600+ 包) → **P2P 已通**,视频/音频在拉流
- 有 `receivers`(RTSP consumer) → RTSP 输出可用

---

## WebUI "Add" 按钮缺陷

WebUI 点击 Add 后，配置**不会自动写入** `go2rtc.yaml`。必须手动写入后 restart：

```bash
# 手动写 stream 配置（等 WebUI Add 设备后执行）
ssh root@192.168.50.1 "cat >> /mnt/user/appdata/go2rtc/go2rtc.yaml << 'EOF'
streams:
  cw300:
    - \"xiaomi://1291104493:cn@192.168.50.66?did=1079924977&model=mxiang.camera.moc001&retries=60&timeout=30s\"
EOF
docker restart go2rtc"
```

然后等 10~15 秒，查 `/api/streams` 看 `bytes_recv` 是否增长。

---

## P2P 失败排查

```
i/o timeout — 原因：
  1. DID 变了（旧 DID 指向的设备不存在了）
  2. 摄像头在局域网但走云端 P2P，双方 NAT 类型不兼容
  3. go2rtc webrtc candidates 未正确配置

检查 webrtc candidates（在 go2rtc.yaml）：
webrtc:
  candidates:
    - "stun:8556"
    - "192.168.50.1:8556"   # 必须填 NAS 实际 IP
```

---

## references/

- `references/go2rtc-yaml-example.md` — 已知正常工作的 go2rtc.yaml 示例（含 token 刷新、DID 清除）
- `references/docker-compose-patch.md` — Unraid docker-compose 只读修复完整步骤