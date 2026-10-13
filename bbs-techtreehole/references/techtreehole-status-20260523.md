# TechTreeHole BBS 当前状态（2026-05-23 最终版）
# TechTreeHole BBS 当前状态（2026-05-23，rebuilding）

## 环境
- **NodeBB**: v4.11.2，Node.js v24.15.0
- **数据库**: Redis（容器名 `nodebb_redis`，无密码）
- **容器网络**: `nodebb_net`（bridge，172.24.0.0/16），两个容器 DNS 互通
- **NAS**: `192.168.50.1`，SSH `root/<PASSWORD_从_gbrain_获取>`
- **iStoreOS 路由**: `123.114.199.136`，SSH `root/<ROUTER_PASSWORD_从_gbrain_获取>`

## Docker 挂载结构（2026-05-23 纠正）
```
nodebb 容器:
  /usr/src/app     → Docker 镜像层（NodeBB 源码）
  /data            → /mnt/user/appdata/nodebb（NAS 持久化，config.json 在这）
  /opt/config      → Docker volume（空的！）
  /usr/local/bin/entrypoint.sh → 入口脚本

nodebb_redis 容器:
  /data            → /mnt/user/appdata/nodebb/redis（NAS 持久化）
```

**重要发现**：entrypoint.sh 读 `/opt/config/config.json`，但这个挂载是空的。config 实际在 `/data/config.json`（挂载到 NAS）。之前手动写 `/mnt/user/appdata/nodebb/config.json`（主机路径）是对的。

## Admin 账号
- uid=1，用户名 `admin`，邮箱 `ianlee168@gmail.com`
- 密码 `<ADMIN_PASSWORD_从_gbrain_获取>`
- **状态**：Redis 已 FLUSHALL，admin 尚未重建

## 2026-05-23 重建过程（进行中）

### 已完成步骤
1. Redis FLUSHALL → 空库
2. `/usr/src/app/setup.json` 预配置写入（admin + Redis 参数）
3. `/data/config.json` 已删除 → NodeBB 进入安装向导模式
4. 安装向导启动：`Web installer listening on http://0.0.0.0:4567`
5. Redis 连接测试通过：`{"success":1,"dbfull":false}`

### 剩余步骤（陛下操作）
浏览器打开 `http://localhost:4567/`：
1. Database Type 下拉框 → 选 "Redis"（当前是 MongoDB）
2. 点击 "Install NodeBB" 按钮
3. 等待安装完成 → admin 账号自动创建，Redis 全量初始化

**注意**：安装向导 POST 受 CSRF + 会话 cookie 保护，curl 无法自动化，必须用浏览器。

### setup.json 内容（已写入）
```json
{
  "defaults": {
    "url": "https://bbs.techtreehole.com:16666",
    "secret": "a55a2f1eb9427de80ce69f95b2aad8011c9051fd8273feaa",
    "admin:username": "admin",
    "admin:password": "<ADMIN_PASSWORD_从_gbrain_获取>",
    "admin:email": "ianlee168@gmail.com",
    "database": "redis",
    "redis:host": "nodebb_redis",
    "redis:port": 6379,
    "redis:database": 0
  }
}
```
写入命令：`docker cp setup.json nodebb:/usr/src/app/setup.json`

## 403 Forbidden 根因（2026-05-23 确认）
NodeBB 登录流程：
1. CSRF 检查 → pass
2. 密码 `password.compare` → pass（容器内 bcryptjs 验证 ✅）
3. **`privileges.global.can('local:login', uid)` → fail**
   - 读 Redis key `privileges:global:local:login` 等
   - 这些 key 手动创建 Redis 时完全没建
4. → 403 Forbidden

## bcryptjs 结论（已澄清）
- **容器内**：bcryptjs `compareSync` 工作正常 ✅
- **host 端（Node.js v24）**：bcryptjs `compareSync` 有 bug，恒返回 false ❌
- 手动 Redis 写入 admin 失败是因为权限数据缺失，不是密码 hash 问题
- **唯一可靠解法：/setup 向导**

## 外网访问
- `https://bbs.techtreehole.com:16666` ✅
- `https://bbs.techtreehole.com`（443）❌
