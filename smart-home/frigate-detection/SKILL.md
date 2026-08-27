---
name: frigate-detection
description: Frigate 物体检测配置坑 — 挂载路径乌龙、detect.enabled 默认关、objects 默认只认 person、猫狗鸟不触发、CPU 推理验证。适用 Frigate 0.17+/Unraid Docker。
triggers:
  - "frigate 没画面"
  - "猫不触发"
  - "检测没反应"
  - "frigate detect"
  - "frigate objects"
  - "摄像头变化弹小画面"
---

# Frigate 物体检测配置

## 三个最坑的默认值/路径

1. **detect.enabled 默认关(Frigate 0.17+)**:config 里 detect 段不写 `enabled: true` = 检测全程关闭,画面正常但永远不识别任何东西。**必须显式写**。
2. **objects 默认只认 person**:不写 `objects.track` 列表 → 只检测人,**猫/狗/鸟永远不触发**。要识别动物必须显式列出。
3. **挂载路径乌龙**:`docker inspect frigate` 看实际挂载的 config 文件——可能是**平铺的** `/mnt/user/appdata/frigate/config.yaml`,而目录 `/mnt/user/appdata/frigate/config/config.yaml` 是**未被使用的旧副本**(改了不生效!)。同理 go2rtc 有 `/mnt/user0/` 旧副本坑。**改前必查 docker inspect**。

## 最小可用配置(检测 + 动物识别 + 快照)

```yaml
detect:
  enabled: true
  width: 640
  height: 480
  fps: 5

objects:
  track:
    - person
    - cat
    - dog
    - bird

snapshots:
  enabled: true

cameras:
  backyard:
    ffmpeg:
      inputs:
        - path: rtsp://<NAS_IP>:8556/<stream_name>
          roles:
            - detect
            - rtmp
```

## 验证检测真的在跑(别信配置,看运行态)

```bash
# 1. 运行态 stats:detection_enabled 必须 true、detection_fps > 0
curl -s http://<NAS_IP>:5000/api/stats | grep -oE '"detection_enabled":(true|false)|"detection_fps":[0-9.]+'

# 2. 有效配置(运行态合并后)的 objects.track
curl -s http://<NAS_IP>:5000/api/config | grep -oE '"track":\[[^]]*\]'

# 3. CPU 推理速度
#    stats 里 detector: cpu, inference_speed 毫秒;40ms 内都算流畅
```

**结果判读**:`detection_enabled: true` + `detection_fps: 2.0` + track 含 cat = 生效。

## "画面有变化弹小画面" = 检测事件

Frigate WebUI(`http://<NAS_IP>:5000/`)的**事件/回顾区**:检测到 person/cat/dog/bird → 自动记录片段 + 快照小图。"1 主画面 + 4 小画面"是**多路摄像头的网格布局**,单摄像头只有 1 个主画面,事件缩略图在回顾区。

## frigate 崩溃循环修复(SQLite WAL 冲突,2026-08-27 实战)

**症状**:frigate 容器 `Restarting (1)` 循环;docker logs 里 `peewee.OperationalError: disk I/O error`(或 `database disk image is malformed`);WebUI 打不开;`docker exec` 进不去。

**根因**:恢复/替换 `frigate.db` 时**没同时清 `frigate.db-wal`(可到几十 MB)和 `frigate.db-shm`** → 新主库 + 旧 WAL 冲突,SQLite 写不进去 → frigate 启动即崩。

**修复(容器内 /config/ 是容器层,宿主机 appdata/*.db 可能是历史遗留,先 `docker inspect frigate` 确认挂载)**:
```bash
docker stop frigate
# 1. 备份损坏库留证
mkdir -p /mnt/user/appdata/frigate/db-backup
docker cp frigate:/config/frigate.db /mnt/user/appdata/frigate/db-backup/frigate.db.corrupt
# 2. 生成干净空 SQLite(有效 header,peewee 会自动建表;本机 python3)
python3 -c "import sqlite3; c=sqlite3.connect('/tmp/empty.db'); c.execute('CREATE TABLE _t(x)'); c.execute('DROP TABLE _t'); c.commit(); c.close()"
touch /tmp/empty-wal /tmp/empty-shm
# 3. 覆盖三个文件(主库 + WAL + SHM 全换干净)
docker cp /tmp/empty.db  frigate:/config/frigate.db
docker cp /tmp/empty-wal frigate:/config/frigate.db-wal
docker cp /tmp/empty-shm frigate:/config/frigate.db-shm
docker start frigate   # 等 ~1 分钟变 healthy
```
**代价**:事件/检测记录清空(录像文件在 /data 挂载,**不丢**);新库从零记录。

## 排查速查

| 症状 | 原因 | 处理 |
|------|------|------|
| 画面有但从不弹事件 | detect.enabled 没写/写了 false | 显式 `enabled: true` |
| 人来触发、猫不触发 | objects 默认只 person | 加 cat/dog/bird 到 track |
| 改了配置不生效 | 改错文件(旧副本) | `docker inspect frigate` 查真实挂载 |
| 检测 fps 0 | detect 关 / 流断 | 查 stats + 摄像头流 |
| 快照没存 | snapshots.enabled false | 开 snapshots |

## 凭证/路径约定

NAS IP、摄像头流地址等:敏感值存 gbrain(`concepts/net-topology`),本仓库只写流程(**公开仓库**)。
