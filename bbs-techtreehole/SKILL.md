---
name: bbs-techtreehole
category: self-hosted
description: bbs.techtreehole.com 论坛（NodeBB）「科技树洞」部署、运维与故障排查。涵盖 Docker/Redis/Mongo 架构、NodeBB 安装向导、版本升级、403/500 排查、admin 密码重置、lucky 反代。
version: 2.2.0
author: ianlee168
platforms: [linux]
tags: [nodebb, forum, techtreehole, redis, mongo, lucky, reverse-proxy]
---

# bbs-techtreehole — 科技树洞论坛运维

## 基础信息

| 项目 | 值 |
|------|-----|
| 域名 | bbs.techtreehole.com |
| 外网 URL | https://bbs.techtreehole.com:16666（DNS A 指向家宽**动态**公网 IP，会变——勿硬编，每次现查 `getent hosts bbs.techtreehole.com`；2026-10-08 实测 111.194.59.132，早前记录 123.114.199.136 已失效。端口 443 由 iStoreOS 自己占着（自签证书 + 对 RFC1918 源返 403），**不是** bbs 入口） |
| 内网 URL | http://192.168.50.1:4567 |
| 软件 | NodeBB v4.16.2（2026-10-13 升级，v4.15.1 → v4.16.2）；当前已为上游最新版 |
| 数据库 | MongoDB（容器 `nodebb-mongo`）+ Redis（容器 `nodebb-redis`），网络 `nodebb_nodebb-net` |
| 反向代理 | iStoreOS 路由器（公网 IP **动态**，2026-10-08 实测 111.194.59.132，勿硬编）Lucky，暴露外网 16666 |
| NAS SSH | root@192.168.50.1 / <PASSWORD_从_gbrain_获取> |
| GitHub Issue | [#14296](https://github.com/NodeBB/NodeBB/issues/14296)（2026-05-29 Closed，官方确认已修） |
| 管理员账号 | 用户名 `ianlee168` 或邮箱 `ianlee168@gmail.com`（**切勿填 admin，系统无此用户**） |
| 小号账号 | 用户名 `iantechth`（uid 2，未绑定邮箱，密码与主号一致） |
| 管理员后台 | `http://192.168.50.1:4567/admin` |
| 管理密码 | `<ADMIN_PASSWORD_从_gbrain_获取>`（两个账号密码均为该值） |
| 邮件服务 | Resend（2026-10-13 替换 SendGrid，`email:from` = `ianlee168@techtreehole.com`） |
| Resend SMTP 用户名 | `resend`（固定值） |
| Resend SMTP 端口 | 587（STARTTLS） |
| Resend Host | `smtp.resend.com` |

## 架构

```
用户 → lucky反代(bbs.techtreehole.com:16666；公网 IP 动态，现查 `getent hosts bbs.techtreehole.com`) → NAS Docker nodebb(:4567)
  └─ nodebb (ghcr.io/nodebb/nodebb:4.16.2，当前最新)
      ├─ nodebb-mongo (MongoDB)
      └─ nodebb-redis (Redis)
```

## Docker 挂载

`/mnt/user/appdata/nodebb/docker-compose.yml`:

```yaml
services:
  mongo:
    image: mongo:7-jammy
    container_name: nodebb-mongo
    restart: unless-stopped
    volumes:
      - /mnt/user/appdata/nodebb/db/mongo:/data/db
    command: mongod --bind_ip 0.0.0.0 --port 27017
    networks:
      - nodebb-net

  redis:
    image: redis:7-alpine
    container_name: nodebb-redis
    restart: unless-stopped
    volumes:
      - /mnt/user/appdata/nodebb/db/redis:/data
    networks:
      - nodebb-net

  nodebb:
    image: ghcr.io/nodebb/nodebb:4.16.2
    container_name: nodebb
    restart: unless-stopped
    depends_on:
      - mongo
      - redis
    ports:
      - 4567:4567
    volumes:
      - /mnt/user/appdata/nodebb/config:/opt/config
      - /mnt/user/appdata/nodebb/public/uploads:/opt/public/uploads
    environment:
      - DB=mongo
      - MONGO_HOST=mongo
      - MONGO_PORT=27017
      - MONGO_NAME=nodebb
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=0
      - URL=https://bbs.techtreehole.com:16666
      - TZ=Asia/Taipei
      - START_BUILD=true
    networks:
      - nodebb-net

networks:
  nodebb-net:
    driver: bridge
```

⚠️ **entrypoint 从 `/opt/config/config.json` 读取配置**，不是 `/usr/src/app/config.json`。

## 全新安装流程

### 准备工作
```bash
ssh root@192.168.50.1
cd /mnt/user/appdata/nodebb

# 清理旧数据（如果重装）
docker compose down -v
rm -f config/config.json
```

### 自动安装（setup.json）

在 `config/setup.json` 写入预配置（向导会自动读取）：

```json
{
  "url": "http://192.168.50.1:4567",
  "admin:username": "admin",
  "admin:password": "<ADMIN_PASSWORD_从_gbrain_获取>",
  "admin:email": "ianlee168@gmail.com",
  "database": "mongo",
  "mongo:host": "mongo",
  "mongo:port": 27017,
  "mongo:database": "nodebb"
}
```

然后启动：

```bash
docker compose up -d
# 等 120 秒让 build + 安装完成
# 浏览器访问 http://192.168.50.1:4567 查看安装向导
```

⚠️ 安装向导 POST 受 CSRF + 会话 cookie 保护，curl 无法自动化，必须用浏览器点 **Install NodeBB**。

### 手动安装（不设 setup.json）

1. 清空 + 触发向导：
```bash
docker compose down -v
rm -f config/config.json
docker compose up -d
sleep 30
```

2. 浏览器打开 `http://192.168.50.1:4567/`
3. Database Type → 选 **MongoDB**
4. 填 `mongo` 作为 host → **Test Database** → 确认 `{"success":1}` → **Install NodeBB**

## 安装后配置

### 通过 Node.js 写入 MongoDB（绕过 CSRF 直接改数据库）

NodeBB 4.x 的站点标题、描述等存储在 MongoDB 的 `objects` 集合中，而不是 Redis（Redis 存的是 SMTP 等配置，对站点标题不生效）。**不要试图用 Redis HSET 修改标题**——改了也不会在前端显示。

正确方式：通过容器内的 Node.js 直接操作 MongoDB：

```javascript
const {MongoClient} = require("mongodb");
async function main() {
  const client = new MongoClient("mongodb://mongo:27017");
  const db = client.db("nodebb");
  await db.collection("objects").updateOne(
    { _key: "config" },
    { $set: { 
        title: "tthbbs", 
        browserTitle: "tthbbs - 科技树洞", 
        description: "站点描述" 
      } 
    }
  );
  await client.close();
}
main().catch(e => console.error(e.message));
```

执行方式：`cat script.js | docker exec -i nodebb node`（通过管道避免 SSH 引号嵌套问题）。

Logo 和品牌名存在 Redis：
```bash
docker exec nodebb-redis redis-cli HSET config 'brand:logo' '/assets/uploads/logo.svg'
docker exec nodebb-redis redis-cli HSET config 'brand:name' 'tthbbs'
docker compose restart nodebb
```

Logo 文件路径注意：
- 上传到 `public/uploads/` 目录后可通过 `/assets/uploads/` 访问
- 不要用 `/uploads/` 路径（返回 302 跳转）

### Favicon（浏览器标签栏小图标）

直接覆盖系统默认文件即可生效，不需要改数据库：

```bash
# 将 SVG favicon（32×32）写入容器
cat /tmp/favicon.svg | docker exec -i nodebb sh -c "cat > /usr/src/app/public/uploads/tthbbs-favicon.svg"

# 覆盖默认 favicon 文件
cat /tmp/favicon.svg | docker exec -i nodebb sh -c "cp /usr/src/app/public/favicon.svg /usr/src/app/public/favicon.svg.bak && cp /usr/src/app/public/uploads/tthbbs-favicon.svg /usr/src/app/public/favicon.svg"
```

重启容器后浏览器访问 `/assets/favicon.svg` 即可看到。所有用户包括外网都会显示新 favicon。

⚠️ NodeBB 可能缓存 favicon，用户需要 Ctrl+F5 强制刷新才能看到变化。

## 每日版本检查（正确姿势，别照抄 cron prompt 里的 curl/grep）

```bash
# 1. 上游最新 tag + 日期
curl -s "https://api.github.com/repos/NodeBB/NodeBB/releases/latest" | grep -oP '"tag_name":\s*"\K[^"]+'
curl -s "https://api.github.com/repos/NodeBB/NodeBB/releases/latest" | grep -oP '"published_at":\s*"\K[^"]+'

# 2. 本机实际版本（**别信"本机 v4.12.0"之类的记忆/ prompt 描述，现查**）
ssh root@192.168.50.1 "docker ps --format '{{.Names}} {{.Image}}' | grep nodebb; docker exec nodebb cat /usr/src/app/package.json | head -5"

# 3. composer bug 残留（**只在 public/src/modules/**，src/client/ 在 master 上已 404）
python3 -c "import urllib.request as u; t=u.urlopen('https://raw.githubusercontent.com/NodeBB/NodeBB/master/public/src/modules/topicThumbs.js').read().decode(); print('bare_require=', t.count(\"require(['composer']\"), 'hooks=', t.count('action:composer.thumbs.updateCount'))"
```

基线（2026-10-10 复核）：v4.10.0 / v4.11.0 / v4.11.1 = bare 2 / hooks 0；v4.12.0 / v4.15.1 / v4.16.2 / master = bare 0 / hooks 2。
判定：latest tag ≥ v4.12.0 且 bare_require = 0 → composer bug 上游已修复。

⚠️ 本 cron job（`5be07b251352`，每日 09:00）的 prompt 已于 2026-10-10 改写：旧版查的是已不存在的 `src/client/topicThumbs.js`（恒 404 → 假"已修复"）+ 用 grep 转义计数（恒假 0，连 v4.11.1 也报 0）。新版 = `public/src/modules/` + python 计数（不带尾部括号）+ **现查本机实际版本**（不信"本机 v4.12.0"这类过期描述）。改前备份 `~/.hermes/patches/jobs.json.bak-20261010_0900-nodebb-prompt`。

## 升级 NodeBB

### 标准升级流程（4.12.0+ 通用）

动 Unraid Docker 升级前必须先备份数据与配置并留存 undo 脚本，严禁直接裸升。升级前/后必须阅读 CHANGELOG。

```bash
ssh root@192.168.50.1
cd /mnt/user/appdata/nodebb

# 0. 查看 GitHub 最新 Release 与 CHANGELOG
curl -s "https://api.github.com/repos/NodeBB/NodeBB/releases/latest" | python3 -c 'import sys, json; d=json.load(sys.stdin); print("Tag:", d["tag_name"]); print("Changelog:\n", d.get("body",""))'

# 1. 完整备份（Redis + Mongo + 配置）
TARGET_TAG="4.16.2" # 替换为目标版本
BACKUP_DIR="/mnt/user/appdata/nodebb/backups/pre-${TARGET_TAG}"
mkdir -p "${BACKUP_DIR}"

docker exec nodebb-redis redis-cli SAVE
cp -r /mnt/user/appdata/nodebb/db/redis "${BACKUP_DIR}/"
docker exec nodebb-mongo mongodump --out /data/db/mongodump_upgrade
cp -r /mnt/user/appdata/nodebb/db/mongo/mongodump_upgrade "${BACKUP_DIR}/mongo"
rm -rf /mnt/user/appdata/nodebb/db/mongo/mongodump_upgrade

cp -r /mnt/user/appdata/nodebb/config "${BACKUP_DIR}/"
cp /mnt/user/appdata/nodebb/docker-compose.yml "${BACKUP_DIR}/"
cp /mnt/user/appdata/nodebb/docker-compose.yml /mnt/user/appdata/nodebb/docker-compose.yml.bak

# 2. 生成可执行 undo 脚本
cat << EOF > /mnt/user/appdata/nodebb/undo-upgrade-${TARGET_TAG}.sh
#!/bin/bash
set -e
echo "正在回滚 NodeBB 到升级前状态..."
cd /mnt/user/appdata/nodebb
cp -f ${BACKUP_DIR}/docker-compose.yml ./docker-compose.yml
rm -rf config && cp -r ${BACKUP_DIR}/config ./config
docker compose stop nodebb
docker compose up -d nodebb
echo "回滚完成！"
EOF
chmod +x /mnt/user/appdata/nodebb/undo-upgrade-${TARGET_TAG}.sh

# 3. 更新 docker-compose.yml 镜像并预拉取
sed -i "s|image: ghcr.io/nodebb/nodebb:.*|image: ghcr.io/nodebb/nodebb:${TARGET_TAG}|" docker-compose.yml
docker pull ghcr.io/nodebb/nodebb:${TARGET_TAG}

# 4. 重建容器并等待自动迁移与 build（官方 entrypoint 自动对比 install_hash.md5 运行 upgrade）
docker compose up -d
# 等待约 60-90 秒
docker logs -f nodebb # 观察 "NodeBB Upgrade Complete!" 和 "NodeBB Ready"

# 5. 端到端健康检查
curl -s -o /dev/null -w 'Index HTTP %{http_code}\n' http://192.168.50.1:4567/
curl -s -o /dev/null -w 'Login HTTP %{http_code}\n' http://192.168.50.1:4567/login
docker exec nodebb cat /usr/src/app/package.json | grep -m1 '"version"'
curl -s http://192.168.50.1:4567/ | grep -o '<title>.*</title>'
```

⚠️ **重要（2026-08-23 实测）：官方 entrypoint 会自动跑数据迁移，不要手动跑 upgrade！**
- 镜像 entrypoint（`/usr/local/bin/entrypoint.sh` 的 `build_forum()`）会对比 `install/package.json` 的 md5 与 `/opt/config/install_hash.md5`，**package.json 变化时自动执行 `nodebb upgrade --config=/opt/config/config.json`**，完成后写回 install_hash.md5
- 实测 2026-08-23 v4.12.0→v4.15.1：compose up 后自动跑了 3 个迁移（activitypubFilterList→core blocklist、backfill trust_proxy、web_push subscriptions→endpoint keys），输出 `NodeBB Upgrade Complete!`
- **不要**用 `docker compose run --rm --entrypoint "" nodebb env CONFIG=... node nodebb upgrade`——绕过 entrypoint 会导致 CONFIG 环境变量未设置，NodeBB 找不到配置直接进 web installer（EADDRINUSE: 4567）
- 验证迁移是否完成：`docker logs nodebb | grep -E "Upgrading|Upgrade Complete"`

### 手动 `./nodebb upgrade`（仅当 entrypoint 未自动跑时才需要）

正常情况官方 entrypoint 在 compose up 时已自动迁移（见上）。只有日志里没有 `Upgrading...` 时才手动执行：

```bash
# 停止 nodebb 容器（保留 mongo/redis）
docker compose stop nodebb

# 在容器内执行升级
docker compose run --rm nodebb sh -c "
  env CONFIG=/opt/config/config.json node nodebb upgrade
"

# 重新启动
docker compose up -d
```

⚠️ 手动跑时**必须**用 `--entrypoint` 默认（不要加 `--entrypoint ""`），且必须传 `CONFIG`——否则 NodeBB 找不到配置会启动 web installer 并因 4567 端口冲突崩溃。

## 故障排查

### NodeBB API & CSRF

NodeBB 的 admin API（如 `/api/admin/email/test`）需要 CSRF token + session cookie，直接 curl 无法调用。
- 直接修改 Redis config hash 对一些设置有效（如 SMTP），但对标题/品牌等无效（存储在 MongoDB）
- 通过容器内 Node.js 调用 nodemailer 可以直接测试 SMTP
- 通过 MongoDB 直接修改 `objects` 集合的 `config` 文档可以改 title/browserTitle/description

### NodeBB 启动后 500 / 页面空白

**原因 1：webpack composer bug（仅 4.11.x 及以下版本）**
`topicThumbs.js` 用 `require(['composer'])` 动态加载 composer 模块，但 webpack 找不到这个模块。

⚠️ **验证陷阱 2（grep 转义假 0）**：`grep -c "require(\['composer'\])" file` 这种带 `\[` 转义的模式经过 shell / JSON 多层传递会被吃掉反斜杠，**任何版本都恒返回 0**（连已知有 bug 的 v4.11.1 也是 0）→ 会得出"已修复"的假结论。**改用 python 精确计数**：`python3 -c "import urllib.request;t=urllib.request.urlopen('https://raw.githubusercontent.com/NodeBB/NodeBB/<tag>/public/src/modules/topicThumbs.js').read().decode();print(t.count(\"require(['composer']\"))"`。对照基线（2026-09-17 实测）：v4.8.1/v4.10.0/v4.11.1 = 2 处裸引用 + 0 hooks；v4.12.0/v4.15.1/v4.15.2/v4.16.0/master = 0 裸引用 + 2 处 `action:composer.thumbs.updateCount` hooks。

⚠️ **验证陷阱 3（尾部括号假 0，2026-09-17 实测）**：检索串写成 `require(['composer'])`（**带尾部 `)`**）在任何版本都返回 0——老版本的 bug 形态是 `require(['composer'], (composer) => {`，闭括号前多了回调参数，带 `)` 的模式永远匹配不到 bug。**基线必须用不带尾部括号的 `require(['composer']`**：v4.11.1 = 2，v4.12.0+ = 0。只看 0 就下"已修复"结论会把 v4.11.x 也误判成已修（cron 任务 prompt 里的 grep 就是这么写的，别照抄）。

⚠️ **验证陷阱（2026-08-06）**：`grep -c "'composer':" webpack.common.js` 返回 0 **不代表 bug 未修复**——官方 v4.12.0 的修法是**移除** `require(['composer'])` 裸引用（hooks 重构），不是加 alias。所以 master 的 webpack.common.js 里 composer alias **永远为 0** 是修复完成的表现。正确验证 = 查 `public/src/modules/topicThumbs.js`（客户端代码已从 src/client/ 迁到 public/src/，旧路径 master 上 404）里 `require(['composer'])` 残留（0 = 已修复）。2026-09-12 实测 v4.15.2 master 残留 0，仅剩 hooks 事件 action:composer.thumbs.updateCount。交叉验证：v4.11.1 的同一文件有 2 处裸引用（第 71、106 行），v4.12.0 起归零——证实修复确实落在 v4.12.0。最新版 v4.16.0（2026-09-16）安全（2026-09-17 复核：loose 计数 0 + 2 hooks）。

**症状**：`🎉 NodeBB Ready` 正常，但所有页面 500，`/login` 返回 500 错误页（`Failed to lookup view! Did you run ./nodebb build?`）。docker logs 可见 webpack ERROR：`Module not found: Error: Can't resolve 'composer'`。

**修复**：**升级到 v4.12.0+**（官方已用 hooks 重构，commit `16c43a4`）。如果暂时不能升级，用以下 workaround：

```bash
# Patch webpack.common.js 添加 composer alias
cat > /tmp/patch-webpack.js << 'SCRIPT'
const fs = require('fs');
const p = '/usr/src/app/webpack.common.js';
let c = fs.readFileSync(p, 'utf8');
c = c.replace(
  "'jquery-ui/widgets': path.resolve(__dirname, 'node_modules/jquery-ui/ui/widgets'),",
  "'jquery-ui/widgets': path.resolve(__dirname, 'node_modules/jquery-ui/ui/widgets'),\n      'composer': path.resolve(__dirname, 'node_modules/nodebb-plugin-composer-default/static/lib/composer'),"
);
fs.writeFileSync(p, c, 'utf8');
console.log('Patched OK');
SCRIPT

cat /tmp/patch-webpack.js | docker exec -i nodebb node
docker commit nodebb nodebb-patched:4.11.0
sed -i 's|image: ghcr.io/nodebb/nodebb:4.11.0|image: nodebb-patched:4.11.0|' /mnt/user/appdata/nodebb/docker-compose.yml
docker compose up -d
```

**注意**：即使 webpack 编译通过，`node nodebb build` 在已运行的容器中会因端口冲突（EADDRINUSE: 4567）导致模板编译可能不完整。此时仍可能 500。用 `docker commit` 方式可以绕过（新容器启动时 4567 未被占用）。

**原因 2：config.json 不存在或被删除**
此时 NodeBB 进入 web installer 模式（监听 4567 但显示安装界面而非论坛）。
**修复**：检查 `/opt/config/config.json` 是否存在，或通过浏览器重新安装。

### NodeBB 启动失败：ENOTFOUND mongo/redis

**症状**：`docker logs nodebb` 显示 `error: Error: getaddrinfo ENOTFOUND nodebb-redis`

**原因**：依赖容器未运行或网络未正确连接。

**修复**：
```bash
# 确保所有容器运行在同一网络
docker network ls | grep nodebb

# 重启依赖容器
docker start nodebb-mongo && docker start nodebb-redis && sleep 3 && docker start nodebb
```

### 内网访问公网域名返回 403（正常现象，不是故障）

**症状**：从内网（NAS 本身 / 同局域网机器）curl `https://bbs.techtreehole.com/` 返回 `HTTP 403`，body 只有一行：

```html
<h1>Forbidden</h1>Rejected request from RFC1918 IP to public server address
```

**这是 lucky/iStoreOS 的 NAT 回环保护**（拒绝 RFC1918 内网源 IP 打公网地址），**不是论坛挂了**。响应没有 CF/NGINX 头、没有 server 头，也很典型。

**正确健康检查方式**（二选一）：
- 内网直连容器：`curl -o /dev/null -w '%{http_code}' http://192.168.50.1:4567/` → 期望 200
- 公网验证必须用**外网出口**（手机 4G/5G 或第三方探针），从内网命不中公网入口

⚠️ 看到内网 403 就报"站点故障"是误报。先看 body 里有没有 `Rejected request from RFC1918 IP`。

### 登录返回 403 Forbidden

**排查顺序：**

1. 检查 `allowLocalLogin`：
```bash
docker exec nodebb-redis redis-cli HGET config allowLocalLogin
# 如果不是 1：
docker exec nodebb-redis redis-cli HSET config allowLocalLogin 1
```

2. 检查 admin 密码 hash：
```bash
docker exec nodebb-redis redis-cli HGET user:1 password
```

3. **检查 privileges 权限数据**（正确格式是 Hash，不是 String）：
```bash
# 验证 key 类型：
docker exec nodebb-redis redis-cli TYPE "privileges:global:local:login"
# 应返回 hash，如果返回 string 说明之前用 SET 建过，先删再重建：
docker exec nodebb-redis redis-cli DEL "privileges:global:local:login"
docker exec nodebb-redis redis-cli HSET "privileges:global:local:login" "" "1"
docker exec nodebb-redis redis-cli HSET "privileges:global:local:register" "" "1"
docker exec nodebb-redis redis-cli HSET "privileges:global:view:categories" "" "1"
```

## 修改 admin 密码与解除登录锁定

### 解除登录错误锁定（Lockout Reset）

NodeBB 4.x 密码连续输错后会触发锁定，锁定状态和失败次数保存在主数据库（MongoDB 的 `objects` 集合）中（键名为 `lockout:<uid>`、`loginAttempts:<uid>` 以及防用户名枚举的 `lockout:dummy`）。**单纯在 Redis 跑 `DEL loginAttempts:1` 无法解除锁定！**

推荐方式：在 NodeBB 容器内调用内置鉴权模块一键解锁：

```bash
docker exec -i nodebb node -e "
const nconf = require('nconf');
nconf.file({ file: '/opt/config/config.json' });
const db = require('./src/database');
(async () => {
  await db.init();
  const User = require('./src/user');
  await User.auth.resetLockout(1);
  await User.auth.resetLockout('dummy');
  console.log('Admin unlocked successfully');
  process.exit(0);
})();
"
```

备选方式：通过 MongoDB 直接删除锁定键：
```bash
docker exec nodebb-mongo mongosh --quiet --eval 'db.getSiblingDB("nodebb").objects.deleteMany({_key: /^(lockout|loginAttempts):/})'
```

### 密码验证机制与 shaWrapped 陷阱

NodeBB 用户密码在数据库中若带有 `'password:shaWrapped': 1`，说明存储的 bcrypt 哈希是先对明文做了 SHA512 包装再算 bcrypt 的：
- 源码逻辑：`password = crypto.createHash('sha512').update(password).digest('hex')`，然后传给 bcrypt。
- 校验密码或代码测试时**必须带第三个参数**：`Password.compare(candidate, user.password, !!user['password:shaWrapped'])`。如果直接比对明文必报 false，会误判为密码错误。

### 修改 admin 密码

```bash
# 1. 生成新 hash（容器内）
docker exec nodebb node -e "
const p = require('./src/password');
p.hash('NEW_PASSWORD').then(h => { console.log(h); process.exit(0); });
"

# 2. 写入 Redis
docker exec nodebb-redis redis-cli SET user:1:password "$2b$12$YOUR_HASH"
docker exec nodebb-redis redis-cli SET user:1:password:shaWrapped 0
docker exec nodebb-redis redis-cli DEL loginAttempts:1
```

⚠️ 手动改密码必须用容器内 node，不要用 host 上的 node（bcryptjs 版本兼容问题）。

### 站点 URL 配置与混合内容（Mixed Content）

当通过公网 HTTPS（如 Lucky 反代 `https://bbs.techtreehole.com:16666`）访问论坛时：
- **必须同步更新两处 URL 配置**：
  1. `/mnt/user/appdata/nodebb/config/config.json` 中的 `"url": "https://bbs.techtreehole.com:16666"`
  2. `/mnt/user/appdata/nodebb/docker-compose.yml` 中的环境变量 `- URL=https://bbs.techtreehole.com:16666`
- **后果与机制**：如果此处保留内网 `http://192.168.50.1:4567`，NodeBB 模板引擎会将页面内所有静态资源、头像、样式表、Canonical 标签及 WebSocket 地址渲染为明文 `http://`，导致现代浏览器（Chrome/Edge）触发 **Mixed Content 混合内容安全警告**，地址栏常驻感叹号“不安全”，并使 Chrome 密码嗅探器与自动保存凭据功能彻底失效。
- 更新后执行 `docker compose up -d nodebb` 重建容器使其生效。

### 登录后浏览器（Chrome）不提示保存密码 / 地址栏“不安全”排查

按以下三层顺序由浅入深排查：

1. **站点 URL 是否为内网 http**：检查页面源码中是否包含明文 `http://` 资源（见上方混合内容章节）。
2. **Lucky SSL 证书链有效性**：通过 `openssl s_client -connect <router_ip>:<port> -servername <domain>` 检查返回的证书是否为有效的公共 CA（如 Let's Encrypt），且证书链（Intermediate CA）完整（`Verify return code: 0 (ok)`）。若使用 Lucky 默认自签证书，Chrome 会强制标记不安全并禁用密码管理器。
3. **Chrome 历史异常权限缓存与“证书有效但连接不安全”悖论**：
   - **典型症状**：换上正规 CA（Let's Encrypt）后，点击地址栏红色警告，弹窗显示 **“证书有效”** 但顶部仍提示 **“您与此网站之间建立的连接不安全，请勿在此输入密码等敏感信息”**，下方且伴随 **【本地网络】（开关已开启）**。
   - **根因分析**：
     - ① 用户此前在自签证书阶段点击过“高级 → 继续前往（不安全）”，Chrome 会在该 Session 中缓存安全降级标记；
     - ② 在局域网内通过 NAT 回环访问 `:16666` 端口时，触发了 Chromium 的 **Private Network Access (PNA)** 本地网络安全保护策略，被判定为穿透本地网络。
   - **解决与验证步骤**：
     - **极速验证**：按 `Ctrl + Shift + N` 打开 Chrome 无痕窗口访问，无痕下无历史豁免标记，通常直接显示安全；
     - **会话修复**：在弹窗中点击 **【重置权限】** → 点击 **【Cookie 和网站数据】** 清除该站数据 → 关闭标签页彻底重开；
     - 按 F12 -> **Application** -> **Storage** -> 点击 **Clear site data**。
4. **NodeBB 前端 Ajax 异步拦截**：`/usr/src/app/public/src/client/login.js` 在提交时调用了 `e.preventDefault()` 阻止原生表单提交，改走 `formEl.ajaxSubmit()`。若浏览器嗅探失效，可指导用户在 `chrome://password-manager/passwords` 手动添加一条对应的 Origin 凭据。

## Migration / 备份

⚠️ **铁律：不要删数据库！** 见下方「数据库删除替代方案」一节。

### 备份 MongoDB

```bash
docker exec nodebb-mongo mongodump --out /data/backup/$(date +%Y%m%d)

# Copy backup off container
docker cp nodebb-mongo:/data/backup/$(date +%Y%m%d) /mnt/user/appdata/nodebb/backups/

### 备份 Redis

```bash
docker exec nodebb-redis redis-cli SAVE
cp -r /mnt/user/appdata/nodebb/db/redis /mnt/user/appdata/nodebb/db/redis.bak.$(date +%Y%m%d)
```

### 完整重置

```bash
docker compose down -v
rm -f /mnt/user/appdata/nodebb/config/config.json
docker compose up -d
```

### 数据库删除替代方案

**永远不要执行 `rm -rf` 删除数据库数据目录。** 如果 postgres / mongo 连不上，先尝试：

1. 检查日志找具体错误：`docker logs nodebb --tail 20 | grep -i error`
2. 如果是密码错误 → 改 `.env` 里的密码或直接在数据库里 `ALTER USER`
3. 如果是端口冲突 → 停掉冲突服务或改端口
4. 如果是 pg_hba.conf 拒绝 → 改为 trust 模式
5. 只有以上都无效时才考虑重建，且必须备份到 `.bak` 目录

Delete operations on data directories are REVERSIBLE on Btrfs. If you run `rm -rf` by mistake on a Btrfs filesystem, check if snapshots exist: `sudo btrfs subvolume list /mnt/user/appdata/nodebb`.

## news.techtreehole.com (InsightHub) — 子域异构陷阱

⚠️ **`news.techtreehole.com` ≠ `bbs.techtreehole.com`**。两者域名相似但**架构完全不同**：
- `bbs.techtreehole.com` — 标准 NodeBB 4.12 + Mongo/Redis（见上方架构）
- `news.techtreehole.com` — 自研 SPA 套壳（"Insight Hub"），不再是 NodeBB

### 关键差异

| 项目 | bbs.*（NodeBB） | news.*（InsightHub SPA） |
|------|-----------------|--------------------------|
| 后端 | NodeBB 4.12 + Mongo + Redis | 自研 worker + D1 / 内部 DB |
| HTML 来源 | NodeBB 模板渲染 | React/Vue SPA 客户端渲染 |
| 标准 NodeBB API | `/api/topic/<id>` 等返回 JSON | **全部被前端接管，返回同一份 shell HTML** |
| `/post/<id>` 渲染 | 服务端渲染 | 客户端 JS 拉数据后渲染 |
| curl 抓 post 正文 | 可以（标准 API + 服务端 HTML） | ❌ **抓不到**（HTML 是空壳，正文由 JS 注入） |
| 写 API | 标准 NodeBB `/api/posts/add` | 自有 `/api/posts/add`（独立鉴权 token） |

### 已验证的路径（2026-06-16）

**❌ 全部不可用（都返回 SPA shell HTML）：**
- `GET /post/<id>` — 空壳 HTML
- `GET /api/topic/<id>` — 空壳 HTML
- `GET /api/post/pid/<id>` — 空壳 HTML
- `GET /api/v3/topics/<id>/posts` — 空壳 HTML
- `GET /api/category/idea` — 空壳 HTML
- `GET /post/<id>.json` — 空壳 HTML
- `r.jina.ai/https://news.techtreehole.com/post/<id>` — jina 也只截到首屏，正文拿不到

**✅ 已确认能用的接口：**
- `POST /api/posts/add`（pipeline 写文章用，需要内部 token）—— **不能拿历史正文**
- 文章正文只能从浏览器渲染的 DOM 抓，或找 InsightHub 自己的内部 read API

### 实操后果

- **想引用昨日发布的 news 文章时**（如早间日报想列 3-5 条标题），curl 完全无能为力——除非 `daily-ai-news` pipeline 在 `~/.hermes/profiles/webui-hermes/cron/output/454f4d9882c7/*.md` 里把 LLM 输出落盘（目前**没有**，只存 post ID + 特效）
- **不要假设 news 站能用 NodeBB 工具链修**——`./nodebb upgrade`、`mongo` 命令等都碰不到 InsightHub 的数据
- **要修 InsightHub 的 bug**（如 2026-06-04 发现的"奇思妙想"文章点击无反应）→ 找 worker 源码（`gbrain-ops` 21 节有相关记录），不是 NodeBB 源码

### 跨域铁律

🚫 **绝不要在 news 站试 bbs 的修复手段**（docker exec nodebb、redis-cli HSET、mongo 改 objects 等）。两边完全隔离。

---

## 主题与皮肤

### Persona + Quartz 不兼容

❌ Persona 主题 + Quartz Bootswatch 皮肤 = 首页排版错乱、特效消失
✅ Harmony 主题 + Quartz Bootswatch 皮肤 = 正常显示

用 MongoDB 修改：

```javascript
// Harmony 主题 + Quartz 皮肤（兼容）
const {MongoClient} = require("mongodb");
const c = new MongoClient("mongodb://mongo:27017");
const d = c.db("nodebb");
await d.collection("objects").updateOne(
  { _key: "config" },
  { $set: { "theme:id": "nodebb-theme-harmony", bootswatchSkin: "quartz", defaultBootswatchSkin: "quartz" } }
);
```

或者用 mongosh：
```bash
docker exec nodebb-mongo mongosh --quiet --eval 'db.getSiblingDB("nodebb").objects.updateOne({_key:"config"},{$set:{"theme:id":"nodebb-theme-harmony",bootswatchSkin:"quartz",defaultBootswatchSkin:"quartz"}})'
```

### Favicon 设置

直接覆盖 `/usr/src/app/public/favicon.svg`，不需要改数据库。

## 邮件配置（SMTP）

NodeBB 4.x 的邮件配置存在 Redis config hash 中。**三个关键点**：
1. 必须设 `email:smtpTransport:enabled = 1`（否则默认用 sendmail，发不出去）
2. 不要在 MongoDB 写嵌套 JSON 对象（会导致读取卡死）
3. **Gmail App Password 不适合用于论坛邮件服务**——Google 会因"异常登录检测"随机封禁，即使同 IP 同设备、使用频率极低也会触发。

设置方式：

### 关键点 1：必须设置 `email:smtpTransport:enabled = 1`

NodeBB 默认用 sendmail（本机发信），**不会自动启用 SMTP**。即使配了 host/port/auth，只要没设这个开关就发不出去。这是最常见的邮件不通原因。

```bash
# 完整 SMTP 配置（带 enabled 开关！）
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:host' smtp.gmail.com
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:port' 465
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:secure' true
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:auth:user' ianlee168@gmail.com
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:auth:pass' '16-char-app-password'
docker exec nodebb-redis redis-cli HSET config 'email:from' 'tthbbs <ianlee168@gmail.com>'

# 重启生效
docker compose restart nodebb
```

### 关键点 2：不要往 MongoDB 写嵌套对象

### 邮件发信服务（Resend）

NodeBB 4.x 的邮件配置存在 Redis config hash 与 MongoDB objects 集合中。目前采用 **Resend**（替代已弃用的 SendGrid / Gmail）。

#### Resend 参数
| 项目 | 值 |
|------|-----|
| 服务器 | `smtp.resend.com` |
| 端口 | `587` |
| 加密 | STARTTLS（`secure: false`） |
| 用户名 | **`resend`**（固定值，不是邮箱） |
| 密码 | Resend API Key（`re_xxxx...`） |
| 发件人 | `tthbbs <ianlee168@techtreehole.com>` |

#### DNS 自动化配置（与 Cloudflare Email Routing 无冲突）
Resend 发信走子域 CNAME (`send`/`rsend`)，完全不碰根域 MX，与现有 Cloudflare Email Routing 转发完美共存：
- TXT `resend._domainkey.techtreehole.com`（DKIM）
- CNAME `rsend.techtreehole.com` -> `rsend-apne1.forge.rmta.net`（SPF，DNS only）
- CNAME `send.techtreehole.com` -> `send.forge.rmta.net`（SPF，DNS only）

#### 写入配置命令
```bash
# Redis 端
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:host' smtp.resend.com
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:port' 587
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:secure' false
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:security' STARTTLS
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:service' 'nodebb-custom-smtp'
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:user' resend
echo "re_your_api_key" | docker exec -i nodebb-redis redis-cli -x HSET config 'email:smtpTransport:pass'
docker exec nodebb-redis redis-cli HSET config 'email:from' 'tthbbs <ianlee168@techtreehole.com>'

# MongoDB 端（后台展示与多处逻辑同步）
docker exec nodebb-mongo mongosh --quiet --eval '
  const db = db.getSiblingDB("nodebb");
  db.objects.updateOne({_key: "config"}, {$set: {
    "email:smtpTransport:host": "smtp.resend.com",
    "email:smtpTransport:port": 587,
    "email:smtpTransport:security": "STARTTLS",
    "email:smtpTransport:user": "resend",
    "email:smtpTransport:pass": "re_your_api_key",
    "email:smtpTransport:service": "nodebb-custom-smtp",
    "email:smtpTransport:enabled": true,
    "email:from": "tthbbs <ianlee168@techtreehole.com>"
  }});
'
docker compose restart nodebb
```

### SendGrid 特殊坑点（遗留记录）

1. **必须先在 SendGrid 后台验证发件人身份（Sender Identity）**，否则返回 `535 Authentication failed`。验证域名不能用免费邮箱（Gmail 不行），必须用自定义域名如 `ianlee168@techtreehole.com`。
2. **用户名固定为 `apikey`**（字符串本身，不是你的邮箱，也不是 API Key 创建时填的名字如 `tthbbs02`）
3. **API Key 在 SendGrid 后台创建后需设为 Full Access 权限**——Restricted Access 会导致 SMTP 认证失败
4. **设置后需要去后台点 "Retry" 或等几分钟生效**
5. **API Key 含特殊字符，写入 Redis 要用文件管道方式**（避免 bash 截断）

### SendGrid SMTP 配置（推荐替代 Gmail）

**为什么不用 Gmail SMTP：** Google 会随机封禁 App Password——即使同一 IP 同一设备、几乎从不使用，也会触发"异常登录检测"返回 `530-5.7.0 Authentication Required`。不适合用于论坛邮件服务。

**SendGrid 免费计划（100 封/月）足够私人论坛使用，API Key 不会随意封禁。**

#### 前置步骤

1. 在 SendGrid 后台注册账号
2. **Settings → Sender Authentication → Verify a Single Sender**—添加发件人地址（如 `ianlee168@techtreehole.com`），收验证邮件点链接确认
3. **Settings → API Keys → Create API Key** → 选 **Full Access**（Restricted Access 会导致 SMTP 认证失败）
4. 记下生成的 API Key

#### 配置参数

| 项目 | 值 |
|------|-----|
| 服务器 | `smtp.sendgrid.net` |
| 端口 | `587` |
| 加密 | STARTTLS（`secure: false`） |
| 用户名 | **`apikey`**（固定值，不是邮箱！SendGrid 后台创建 API Key 时填的名字 `tthbbs02` 是 Key 的名字，不是 SMTP 用户名） |
| 密码 | API Key（Full Access） |

#### 写入 Redis（Linux/Mac）

```bash
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:host' smtp.sendgrid.net
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:port' 587
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:secure' false
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:user' apikey
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:pass' 'SG.xxx...'
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
docker exec nodebb-redis redis-cli HSET config 'email:from' 'tthbbs <ianlee168@techtreehole.com>'
docker compose restart nodebb
```

⚠️ **关键：必须同时设 `user`/`pass` 和 `enabled`**。NodeBB 4.12 读的是 `email:smtpTransport:user` 和 `email:smtpTransport:pass`（不是 `auth:user`/`auth:pass`——老版本才用带 `auth:` 的 key）。

⚠️ **必须设 `email:smtpTransport:enabled = 1`**，否则 NodeBB 默认用 sendmail（本机发信），即使配了 host/port/auth 也不会走 SMTP。

#### API Key 安全写入（避免 bash 截断）

API Key 含特殊字符，直接写在 bash 命令行可能被截断：

```bash
# 正确方式：echo → ssh → redis-cli -x（从 stdin 读）
echo 'SG.your_full_api_key_here' | ssh root@nas 'docker exec -i nodebb-redis redis-cli -x HSET config "email:smtpTransport:pass"'

# 或者写文件到 NAS，再管道给 redis-cli
cat /tmp/key.txt | ssh root@nas 'docker exec -i nodebb-redis redis-cli -x HSET config "email:smtpTransport:pass"'
```

#### 验证 SMTP 是否工作

容器内直接测试（不依赖 NodeBB 邮件系统）：

```bash
cat > /tmp/test-sg.js << 'SCRIPT'
const nodemailer = require("nodemailer");
const t = nodemailer.createTransport({
  host: "smtp.sendgrid.net", port: 587, secure: false,
  auth: { user: "apikey", pass: "SG.xxx..." }
});
t.sendMail({
  from: "ianlee168@techtreehole.com",
  to: "ianlee168@gmail.com",
  subject: "SendGrid Test",
  html: "<p>test</p>"
}).then(i => console.log("Sent:", i.messageId))
.catch(e => console.log("Error:", e.message));
SCRIPT
cat /tmp/test-sg.js | ssh root@nas 'docker exec -i nodebb node'
```

#### 验证新用户注册能否收到邮件

1. 在 BBS 注册一个新账号
2. 检查 `docker logs nodebb | grep -i email` 看报错
3. 如果报 `535 Authentication failed` → 检查 API Key 是否为 Full Access，发件人是否已验证
4. 如果报 `530 Authentication Required` → 说明 Gmail App Password 被封了，切 SendGrid

#### SendGrid 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `535 Authentication failed: The provided authorization grant is invalid, expired, or revoked` | API Key 权限不足、被吊销或发件人未验证 | 1. 确认 API Key 是 Full Access 2. 确认发件人已在 Sender Authentication 验证 3. 重新生成 API Key |
| `451 Authentication failed: Maximum credits exceeded` | SendGrid 免费额度耗尽或试用期结束 | 邮件被 SendGrid 本地拦截未发出（勿误判为下游 Cloudflare 转发故障）。换新 Key 或切换到 Resend |
| 小号急需绑定邮箱但发信挂了 | 发信服务不可用时绕过邮件确认 | 直接在 MongoDB 强刷：`docker exec nodebb-mongo mongosh --quiet --eval 'db.getSiblingDB("nodebb").objects.updateOne({_key:"user:<uid>"},{$set:{email:"user@domain.com","email:confirmed":1}})'` |
| 后台测试按钮报错但直连 nodemailer 能发 | NodeBB 4.12 后台测试走的是不同的代码路径 | 忽略后台测试，以实际注册验证邮件为准 |
| `connect ECONNREFUSED 127.0.0.1:587` | `email:smtpTransport:service` 不是 `nodebb-custom-smtp`，导致 NodeBB 不读 host/port——源码 `/usr/src/app/src/emailer.js` 第 139 行检查 `if (config['email:smtpTransport:service'] === 'nodebb-custom-smtp')`，如果 service 不是这个值，host/port 不生效，直接连 127.0.0.1 | 设置 `HSET config 'email:smtpTransport:service' 'nodebb-custom-smtp'` |
| 后台 Email 页面显示 Gmail 配置但实际已是 SendGrid | MongoDB 存了旧数据，后端读的是 Redis | 用 mongosh 更新 MongoDB：`objects.updateOne({_key:"config"}, {$set:{"email:smtpTransport:host":"smtp.sendgrid.net", ...}})` |

**验证邮件是否发送成功：**
```bash
docker logs nodebb 2>&1 | grep -i 'email\\|mail\\|smtp'
```

**直接测试 SMTP 连接（不依赖 NodeBB）：**
```bash
cat > /tmp/nbb-test-smtp.js << 'SCRIPT'
const nodemailer = require("nodemailer");
const transporter = nodemailer.createTransport({
  host: "smtp.gmail.com", port: 465, secure: true,
  auth: { user: "ianlee168@gmail.com", pass: "<GMAIL_APP_PASSWORD_从_gbrain_获取>" }
});
transporter.sendMail({
  from: "ianlee168@gmail.com", to: "ianlee168@gmail.com",
  subject: "Test", html: "<p>test</p>"
}).then(info => console.log("Sent:", info.messageId))
.catch(err => console.log("Error:", err.message));
SCRIPT
cat /tmp/nbb-test-smtp.js | docker exec -i nodebb node
```

## techtreehole Telegram Bot

独立 bot，监听 @techtreehole 频道转发内容到 news worker。

| 项目 | 值 |
|------|-----|
| 源码 | `/home/ianlee168/techtreehole-bot/bot.py` |
| 工作目录 | `/home/ianlee168/techtreehole-bot` |
| 启动命令 | `cd /home/ianlee168/techtreehole-bot && BOT_TOKEN=*** python bot.py` |
| Bot token | `8553403978:***`（username: pixelclaw168_bot）|
| 已知 bug | line 265 缺少 `startup_polls = 0` 初始化（已修复） |

⚠️ 启动时必须 `cd` 到正确目录再运行，否则 import 路径会错。

### SMTP / Branding 操作方式（绕过 CSRF + 避免引号截断）

NodeBB 4.x 的 admin API 受 CSRF 保护，无法用 curl 直接调用。以下方式绕过：

**通用技巧：用 `cat 文件 | docker exec -i 容器 命令` 避免 SSH 引号嵌套截断**

```bash
# write_file 创建脚本文件到 /tmp/xxx.js
# 然后管道执行（不嵌套引号，不会截断）
cat /tmp/xxx.js | ssh root@nas 'docker exec -i nodebb node'
```

如果通过 execute_code 用 terminal()，Python 会处理转义，也比手写 SSH 命令稳。

**方式 1：Redis HSET（对 SMTP 配置有效）**
```bash
### SMTP / Branding 操作方式（绕过 CSRF）

NodeBB 4.x 的 admin API 受 CSRF 保护，无法用 curl 直接调用。有三种方式可以绕过：

**方式 1：Redis HSET（对 SMTP 配置有效）**
```bash
docker exec nodebb-redis redis-cli HSET config email:smtpTransport:host smtp.gmail.com
```

**方式 2：MongoDB 直接修改（对站点标题/品牌有效）**
```javascript
const {MongoClient} = require("mongodb");
const client = new MongoClient("mongodb://mongo:27017");
const db = client.db("nodebb");
await db.collection("objects").updateOne(
  { _key: "config" },
  { $set: { title: "tthbbs", browserTitle: "tthbbs - 科技树洞" } }
);
```

**方式 3：容器内 nodemailer 测试邮件（不依赖 NodeBB 邮件系统）**
```javascript
const nodemailer = require("nodemailer");
const t = nodemailer.createTransport({
  host: "smtp.gmail.com", port: 465, secure: true,
  auth: { user: "ianlee168@gmail.com", pass: "app-password" }
});
t.sendMail({ from, to, subject, html });
```
用 `cat script.js | docker exec -i nodebb node` 执行（避免引号嵌套问题）。

⚠️ 注意：`brand:logo` 在 MongoDB 中存的是字符串键 `"brand:logo"`（不是对象 `brand.logo.url`）。
Logo 文件路径要用 `/assets/uploads/xxx.svg`（不是 `/uploads/`，后者返回 302）。
Favicon 可以直接覆盖 `/usr/src/app/public/favicon.svg`。

### SMTP 更换（Gmail → SendGrid）

SendGrid SMTP 参数：
- 服务器：`smtp.sendgrid.net`
- 端口：`587`（TLS）
- 用户名：固定字符串 `apikey`（不是邮箱或用户名）
- 密码：SendGrid 生成的 API Key

配置方法（Redis + MongoDB 都要改）：
```bash
# Redis
docker exec nodebb-redis redis-cli HSET config "email:smtpTransport:host" smtp.sendgrid.net
docker exec nodebb-redis redis-cli HSET config "email:smtpTransport:port" 587
docker exec nodebb-redis redis-cli HSET config "email:smtpTransport:secure" false
docker exec nodebb-redis redis-cli HSET config "email:smtpTransport:auth:user" apikey
docker exec nodebb-redis redis-cli HSET config "email:smtpTransport:auth:pass" "SG.xxx.."
docker exec nodebb-redis redis-cli HSET config "email:smtpTransport:enabled" 1
docker exec nodebb-redis redis-cli HSET config "email:from" "tthbbs <sender@domain.com>"

# MongoDB (for admin panel display)
docker exec nodebb-mongo mongosh --quiet --eval '
  var db = db.getSiblingDB("nodebb");
  db.objects.updateOne({_key:"config"},{$set:{
    "email:smtpTransport:host":"smtp.sendgrid.net",
    "email:smtpTransport:port":587,
    "email:smtpTransport:security":"STARTTLS",
    "email:smtpTransport:user":"apikey",
    "email:smtpTransport:pass":"SG.xxx..",
    "email:smtpTransport:enabled":true,
    "email:from":"tthbbs <sender@domain.com>"
  }});
'
```

**NodeBB 4.12 SMTP code path (2026-06-01 discovery):**
The emailer reads config keys in this order:
1. `email:smtpTransport:service` — if `'nodebb-custom-smtp'`, reads host/port/security
2. Otherwise, skips host/port and uses presets
3. SMTP user: `email:smtpTransport:user` (NOT `email:smtpTransport:auth:user`)
4. SMTP pass: `email:smtpTransport:pass` (NOT `email:smtpTransport:auth:pass`)

If the admin panel test button fails but `nodemailer.createTransport()` in the container works, it's because the admin test uses a different code path than the actual email sender.

API Key 写入注意事项：
- `echo "key" | ssh host "docker exec -i redis redis-cli -x HSET config key"` — `-x` reads from stdin, avoids shell truncation of special characters

## 相关文档

- NodeBB 官方文档：https://docs.nodebb.org
- lucky 反代：iStoreOS 路由器后台（root@192.168.50.1:80）
- 历史 webpack bug 详细记录：`references/webpack-bug-historical.md`
- Shell 引号嵌套截断与安全远程执行：`references/shell-quote-workaround.md`
- SMTP 配置完整指南（Gmail + SendGrid + NodeBB 4.12 细节）：`references/smtp-setup-nodebb.md`
- BBS 健康检查：`scripts/verify-bbs.sh`
- lcz.me 论坛 UI 设计参考：`references/lcz-me-design-notes.md`
- 2026-05-23 重建状态记录：`references/techtreehole-status-20260523.md`

## SMTP 配置核心要点（v4.12+）

NodeBB 4.12 的 SMTP 有三个关键配置必须同时正确：

1. **Redis config hash** 存 `email:smtpTransport:xxx` 系列 key
2. **密码 key 名是 `email:smtpTransport:pass`**（不是 `email:smtpTransport:auth:pass`——那是旧版或后台保存的格式）
3. **`email:smtpTransport:service` 必须是 `nodebb-custom-smtp`**，否则源码里（`/usr/src/app/src/emailer.js` 第 139 行）不会读取 host/port，直接报错 `ECONNREFUSED 127.0.0.1:587`
4. **`email:smtpTransport:enabled` 必须为 `1`**（字符串或数字均可），否则 fallback 到 sendmail
5. **发件人地址必须在邮件服务商后台已验证**

```
user = email:smtpTransport:user          # ← 填 apikey
pass = email:smtpTransport:pass          # ← 填 API Key（不是 auth:pass）
host = email:smtpTransport:host          # ← 只有 service='nodebb-custom-smtp' 时才读
port = email:smtpTransport:port          # ← 同上
service = nodebb-custom-smtp             # ← 关键！不设这个 host/port 不生效
enabled = 1                              # ← 关键！不设这个不走 SMTP
```

⚠️ 千万不要因为 SMTP 密码不对就删除 postgres 数据或重建容器——改 Redis 里对应的 key 即可。**能改配置解决的问题绝不删数据重建。**

## 操作铁律

⚠️ **任何涉及数据删除的操作（rm -rf、容器重建、数据库删除）必须先问陛下。** 能改配置解决的问题绝不删数据重建。操作前记录当前状态，留好 undo 路径。
