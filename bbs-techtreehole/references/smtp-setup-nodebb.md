# NodeBB SMTP 配置指南（v4.12+ / v4.16+）

## 关键发现

NodeBB 4.x 的 SMTP 配置读取逻辑：

1. **Redis config hash** 是主要存储位置
2. **emailer.js 读取的 key 名**：`email:smtpTransport:user`, `email:smtpTransport:pass`, `email:smtpTransport:host`, `email:smtpTransport:port`, `email:smtpTransport:security`, `email:smtpTransport:service`, `email:smtpTransport:enabled`
3. **重要**：当 `email:smtpTransport:service === 'nodebb-custom-smtp'` 时才会读取 host/port/security；否则使用预设服务直接回环 127.0.0.1 导致 ECONNREFUSED
4. **密码字段**是 `email:smtpTransport:pass` (NOT `email:smtpTransport:auth:pass`)
5. **MongoDB** 中也有 `objects` 集合存有 SMTP 配置，后台管理界面与部分逻辑读此集合，改动时需 Redis + MongoDB 双写

## Resend 配置（推荐，替代 SendGrid/Gmail）

Resend 免费版提供 3000 封/月（100 封/天），且对个人论坛极少出现误封。

### 1. 域名 DNS 记录（Cloudflare DNS 自动化）
Resend 发信采用独立子域 CNAME (`send`/`rsend`)，完全不干扰主域名的 Cloudflare Email Routing MX 记录：
- TXT `resend._domainkey.<domain>`: `p=MIGf...`（DKIM 验签）
- CNAME `rsend.<domain>`: `rsend-apne1.forge.rmta.net`（SPF 回弹，DNS only，proxied=false）
- CNAME `send.<domain>`: `send.forge.rmta.net`（SPF，DNS only，proxied=false）

自动化打入命令示例（使用 cfo 工具）：
```bash
~/bin/cfo dns records create -z <ZONE_ID> --body '{"name":"resend._domainkey.<domain>","type":"TXT","content":"<DKIM_VALUE>","ttl":1}'
~/bin/cfo dns records create -z <ZONE_ID> --body '{"name":"rsend.<domain>","type":"CNAME","content":"rsend-apne1.forge.rmta.net","proxied":false,"ttl":1}'
~/bin/cfo dns records create -z <ZONE_ID> --body '{"name":"send.<domain>","type":"CNAME","content":"send.forge.rmta.net","proxied":false,"ttl":1}'
```

### 2. NodeBB 写入配置
```bash
# Redis 端
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:host' smtp.resend.com
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:port' 587
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:secure' false
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:security' STARTTLS
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:service' 'nodebb-custom-smtp'
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:user' resend
echo "re_your_api_key_here" | docker exec -i nodebb-redis redis-cli -x HSET config 'email:smtpTransport:pass'
docker exec nodebb-redis redis-cli HSET config 'email:from' 'tthbbs <verified-sender@yourdomain.com>'

# MongoDB 端（后台管理界面同步）
docker exec nodebb-mongo mongosh --quiet --eval '
  const db = db.getSiblingDB("nodebb");
  db.objects.updateOne({_key: "config"}, {$set: {
    "email:smtpTransport:host": "smtp.resend.com",
    "email:smtpTransport:port": 587,
    "email:smtpTransport:security": "STARTTLS",
    "email:smtpTransport:user": "resend",
    "email:smtpTransport:pass": "re_your_api_key_here",
    "email:smtpTransport:service": "nodebb-custom-smtp",
    "email:smtpTransport:enabled": true,
    "email:from": "tthbbs <verified-sender@yourdomain.com>"
  }});
'
docker compose restart nodebb
```

注意：
- **用户名固定为 `resend`**（不是邮箱，也不是 API Key 名）
- **密码填写 Resend API Key**（`re_xxxx...`）

## SendGrid 配置与坑点

```bash
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:host' smtp.sendgrid.net
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:port' 587
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:security' STARTTLS
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:service' 'nodebb-custom-smtp'
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:user' apikey
echo "YOUR_SENDGRID_API_KEY" | docker exec -i nodebb-redis redis-cli -x HSET config 'email:smtpTransport:pass'
docker exec nodebb-redis redis-cli HSET config 'email:from' 'verified-sender@yourdomain.com'
```

注意：
- **用户名固定为 `apikey`**
- **451 Maximum credits exceeded 或 535 Authentication failed**：免费账号试用期结束后配额耗尽或被风控挂起，邮件在发件端直接抛错（压根没出站），勿误判为下游收件转发故障。遇到此报错应直接换用 Resend。

## 测试 SMTP 连接

直接在容器内用 Node.js 调 nodemailer 进行连通性与实发测试最靠谱（不依赖 NodeBB 后台）：

```bash
cat > /tmp/test-smtp.js << 'SCRIPT'
const nodemailer = require("nodemailer");
const transport = nodemailer.createTransport({
  host: "smtp.resend.com", port: 587, secure: false,
  auth: { user: "resend", pass: "re_your_api_key_here" }
});
transport.sendMail({
  from: "tthbbs <verified-sender@yourdomain.com>",
  to: "your-email@gmail.com",
  subject: "SMTP Test", html: "<p>Test successful!</p>"
}).then(i => console.log("Sent successfully! MessageId:", i.messageId))
.catch(e => console.error("Error:", e.message));
SCRIPT
cat /tmp/test-smtp.js | docker exec -i nodebb node
```

## 排查清单

1. 容器内直连 nodemailer 测试 — 绕过 NodeBB 复杂路由直接测 SMTP 响应
2. 确认 `email:smtpTransport:service === 'nodebb-custom-smtp'`（缺少此项会导致 host/port 完全被忽略）
3. 确认 `email:smtpTransport:enabled === 1`
4. 确认 `email:smtpTransport:pass` 字段存在（不是旧版的 `auth:pass`）
5. 确认发件人域名在 Resend/SendGrid 已通过 DKIM/SPF 验证
