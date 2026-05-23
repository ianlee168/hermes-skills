---
name: bbs-techtreehole
category: self-hosted
description: bbs.techtreehole.com 论坛（NodeBB）「科技树洞」部署、运维与故障排查。
version: 1.0.0
author: ianlee168
platforms: [linux]
---

# bbs-techtreehole — 科技树洞论坛运维

## 基础信息

| 项目 | 值 |
|------|-----|
| 域名 | bbs.techtreehole.com |
| 端口 | 16666（容器直接暴露，不走 443） |
| 外网 URL | https://bbs.techtreehole.com:16666 |
| 内网 URL | http://192.168.50.1:16666（NAS）或 http://localhost:16666（路由器端口转发） |
| 软件 | NodeBB v3.x |
| 数据库 | Redis（容器 `nodebb_redis`，网络 `nodebb_net`） |
| 反向代理 | iStoreOS 路由器上的 Lucky（123.114.199.136），暴露外网 16666 |
| 建站时间 | 2026-05 |

## 架构

```
用户 → lucky 反代(123.114.199.136:16666) → NAS Docker(nodebb:16666) → nodebb + nodebb_redis
                                                                                ↓
                                                                         Redis 数据卷
                                                                    /mnt/user/appdata/nodebb/redis
```

**关键路径：**
- NodeBB 容器内：`/usr/src/app`
- Redis 数据（主机）：`/mnt/user/appdata/nodebb/redis`
- 容器内 Redis 数据：`/data`（映射到主机 `/mnt/user/appdata/nodebb/redis`）
- NodeBB config：`/opt/config/config.json`（容器内路径，**注意：entrypoint.sh 里写的是这个路径但实际为空**）
- NodeBB config 实际路径：看容器挂载
- Redis 容器网络：`nodebb_net`，IP `172.24.0.2`，NodeBB 容器 IP `172.24.0.3`
- Redis DNS：`nodebb_redis`（在同一网络内可解析）

## 容器管理

```bash
# SSH 到 NAS
ssh root@192.168.50.1

# 查看容器状态
docker ps | grep nodebb

# 重启 NodeBB
docker restart nodebb

# 查看 NodeBB 日志
docker logs nodebb 2>&1 | tail -30

# 重启 Redis
docker restart nodebb_redis

# Redis 手动命令
docker exec nodebb_redis redis-cli KEYS "*"
docker exec nodebb_redis redis-cli GET config:allowLocalLogin
docker exec nodebb_redis redis-cli FLUSHALL   # 清空所有数据（重置论坛）
```

## 初始化/重装安装向导

当 `/opt/config/config.json` 不存在且 Redis 为空时，NodeBB 自动进入安装向导（端口 4567）。

**快速初始化（推荐方式）：**

1. 清空 Redis + 删除 config：
```bash
docker exec nodebb_redis redis-cli FLUSHALL
docker exec nodebb sh -c 'echo "172.24.0.2 nodebb_redis" >> /etc/hosts'  # 确保 DNS 解析
# 删除 config
docker exec nodebb rm -f /data/config.json /opt/config/config.json 2>/dev/null
docker restart nodebb
sleep 5
```

2. 浏览器打开 http://localhost:4567/，填表单：
   - 数据库选 **Redis**，host 填 `nodebb_redis`，port `6379`
   - 填 admin 账号信息
   - 点「Test Database」确认连接成功
   - 点「Install NodeBB」

**setup.json 预配置方式：**
```bash
# 写入预配置（admin 信息、Redis 参数），安装向导 POST 时自动读取
docker exec nodebb sh -c 'cat > /usr/src/app/setup.json << EOF
{
    "defaults": {
        "url": "https://bbs.techtreehole.com:16666",
        "admin:username": "admin",
        "admin:password": "R4e3w2q1!",
        "admin:email": "ianlee168@gmail.com",
        "database": "redis",
        "redis:host": "nodebb_redis",
        "redis:port": 6379,
        "redis:database": 0
    }
}
EOF'
docker restart nodebb
```
setup.json 的值在安装向导 POST 提交时通过 nconf 生效（不传给前端表单显示）。

## 故障排查

### 登录返回 403 Forbidden

**排查顺序：**

1. 检查 `allowLocalLogin`：
```bash
docker exec nodebb_redis redis-cli HGET config allowLocalLogin
# 如果不是 1：
docker exec nodebb_redis redis-cli HSET config allowLocalLogin 1
```

2. 检查 admin 密码 hash 是否存在：
```bash
docker exec nodebb_redis redis-cli GET user:1:password
```

3. 检查 bcryptjs 是否正常（容器内）：
```bash
docker exec nodebb node -e "const p=require('./src/password'); p.hash('test').then(h=>console.log('ok')).catch(e=>console.error(e.message))"
```

4. 检查 privileges 权限数据：
```bash
docker exec nodebb_redis redis-cli KEYS "privileges:*"
docker exec nodebb_redis redis-cli KEYS "group:administrators"
# 如果 administrators 组不存在，手动创建：
docker exec nodebb_redis redis-cli SADD "members:administrators" 1
docker exec nodebb_redis redis-cli HSET "group:administrators" name "administrators" description "Administrators" 2 1
```

5. 如果以上都正常但仍 403，检查 NodeBB 日志里的 `error: POST /login`：
```bash
docker logs nodebb 2>&1 | grep -i 'login\|privileges\|can('
```

### 安装向导一直卡在 "Your NodeBB is being installed"

- 检查子进程是否在跑：`docker exec nodebb ps aux | grep node`
- 如果没有子进程，说明 `app --setup` 启动后立刻退出了
- 常见原因：Redis host 解析失败 → **必须加 hosts 映射**：
```bash
docker exec nodebb sh -c 'echo "172.24.0.2 nodebb_redis" >> /etc/hosts'
```

### 500 / 502 错误

```bash
docker logs nodebb 2>&1 | grep -i error | tail -10
```

### 修改 admin 密码（通过 Redis）

```bash
# 生成新 hash（容器内）
docker exec nodebb node -e "
const p = require('./src/password');
p.hash('NEW_PASSWORD').then(h => {
  console.log(h);
  process.exit(0);
});
"
# 然后：
docker exec nodebb_redis redis-cli SET user:1:password "$2b$12$YOUR_HASH_HERE"
```

## 迁移/备份

### 备份 Redis 数据

```bash
# 在 NAS 上
cp -r /mnt/user/appdata/nodebb/redis /mnt/user/appdata/nodebb/redis.bak.$(date +%Y%m%d)
```

### 完整重置论坛

```bash
ssh root@192.168.50.1
docker exec nodebb_redis redis-cli FLUSHALL
docker exec nodebb rm -f /data/config.json /opt/config/config.json 2>/dev/null
docker restart nodebb
# 然后重新走安装向导
```

## 相关文档

- NodeBB 官方文档：https://docs.nodebb.org
- Lucky 反代配置：见 iStoreOS 路由器（root@192.168.50.1:80）
- gbrain memory: `skill_view(name='gbrain')` — 记忆系统里也存了建站笔记
