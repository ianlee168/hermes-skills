# NodeBB 邮件/品牌/主题快速参考

## 配置存储结构（关键区别）

| 配置类型 | 存储位置 | 修改方式 |
|---------|---------|---------|
| 站点标题/描述 | MongoDB `objects.config` | `mongosh` 或 `docker exec nodebb node` |
| 主题/皮肤 | MongoDB `objects.config` | 同上 |
| SMTP 邮件 | **Redis** `config` hash + **MongoDB** `objects.config` | 两者都要写 |
| Logo/Favicon | MongoDB `objects.config` + 文件系统 | 文件 + mongosh |
| 品牌名 | Redis `config` hash | `redis-cli HSET` |

## 邮件配置（Gmail SMTP）

**MongoDB 写入 SMTP（NodeBB 4.12 需要）：**
```javascript
const {MongoClient} = require("mongodb");
const c = new MongoClient("mongodb://mongo:27017");
const d = c.db("nodebb");
await d.collection("objects").updateOne(
  { _key: "config" },
  { $set: {
    "email:smtpTransport:host": "smtp.gmail.com",
    "email:smtpTransport:port": 465,
    "email:smtpTransport:secure": true,
    "email:smtpTransport:auth:user": "ianlee168@gmail.com",
    "email:smtpTransport:auth:pass": "app-password-16-chars",
    "email:smtpTransport:pool": true,
    "email:from": "tthbbs <ianlee168@gmail.com>"
  }}
);
```

**Redis 也要设（NodeBB 读 Redis 判断 SMTP 存在）：**
```bash
docker exec nodebb-redis redis-cli HSET config 'email:smtp:host' smtp.gmail.com
docker exec nodebb-redis redis-cli HSET config 'email:smtp:port' 465
docker exec nodebb-redis redis-cli HSET config 'email:smtp:secure' 'true'
docker exec nodebb-redis redis-cli HSET config 'email:smtp:auth:user' 'ianlee168@gmail.com'
docker exec nodebb-redis redis-cli HSET config 'email:smtp:auth:pass' 'dfyt...'
docker exec nodebb-redis redis-cli HSET config 'email:from' 'tthbbs <ianlee168@gmail.com>'
```

⚠️ **注意**：**不要**在 MongoDB 里写入 `email:smtpTransport` 作为**嵌套 JSON 对象**（`{host:..., port:...}`）——这会把 NodeBB 的 MongoDB driver 搞卡死（超时 15s+）。必须用展平的 `email:smtpTransport:host`、`email:smtpTransport:port` 这样的字符串 key。

**直接测试 SMTP（不依赖 NodeBB 邮件系统）：**
```javascript
const nm = require("nodemailer");
const t = nm.createTransport({
  host: "smtp.gmail.com", port: 465, secure: true,
  auth: { user: "ianlee168@gmail.com", pass: "dfyt..." }
});
t.sendMail({
  from: "ianlee168@gmail.com",
  to: "ianlee168@gmail.com",
  subject: "test",
  html: "<p>test</p>"
}).then(i => console.log("Sent:", i.messageId))
  .catch(e => console.log("Err:", e.message));
```
执行：`cat script.js | docker exec -i nodebb node`

## 主题+皮肤配置

**Harmony + Quartz 搭配（推荐，兼容性好）：**
```bash
docker exec nodebb-mongo mongosh --quiet --eval '
  db.getSiblingDB("nodebb").objects.updateOne(
    {_key:"config"},
    {$set:{"theme:id":"nodebb-theme-harmony", bootswatchSkin:"quartz", defaultBootswatchSkin:"quartz"}}
  ); print("done");
'
```

**Persona 主题不支持 Bootswatch 皮肤**——设了皮肤会导致排版混乱。

## Logo 与 Favicon

| 资源 | 路径 | 注意 |
|------|------|------|
| Logo 文件 | `/usr/src/app/public/uploads/` | 通过 `/assets/uploads/` 访问 |
| Logo 配置 | MongoDB: `brand:logo` (string) | 值：`/assets/uploads/xxx.svg` |
| 品牌名 | Redis: `brand:name` | `redis-cli HSET` |
| Favicon | 覆盖 `/usr/src/app/public/favicon.svg` | 不影响已有用户（Ctrl+F5 刷新） |

**Logo 路径坑**：MongoDB 的 `brand:logo` 存的是普通字符串，不是对象。用 `$set: { "brand:logo": "/assets/uploads/logo.svg" }`。不要写成 `{brand:{logo:{url:...}}}`。

**Favicon 覆盖（最简单）：**
```bash
cat /path/to/favicon.svg | docker exec -i nodebb sh -c "cat > /usr/src/app/public/favicon.svg"
```

## 执行方式：管道胜过 SSH 嵌套引号

当需要在容器内执行 Node.js 脚本时，**永远用管道**而不是 SSH 字符串嵌套：
```bash
# ✅ 好
cat script.js | ssh host "docker exec -i nodebb node"

# ❌ 坏（引号嵌套 100% 会炸）
ssh host "docker exec nodebb node -e \"...\""
```

把脚本写入 `/tmp/xxx.js` 后用 `cat` 管道过去，避免 bash 引号嵌套带来的奇怪截断问题。
