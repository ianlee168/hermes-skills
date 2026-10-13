# SMTP 故障排查（Gmail App Password）

## 快速诊断

```bash
# 1. 检查日志有没有 530 错误
docker logs nodebb 2>&1 | grep '530\|Authentication Required'

# 2. 直接测试 SMTP（绕过 NodeBB）
cat > /tmp/smtp-test.js << 'SCRIPT'
const nodemailer = require("nodemailer");
const t = nodemailer.createTransport({
  host: "smtp.gmail.com", port: 465, secure: true,
  auth: { user: "ianlee168@gmail.com", pass: "xxxxxxxxxxxxxxxx" }
});
t.sendMail({
  from: "ianlee168@gmail.com", to: "ianlee168@gmail.com",
  subject: "Test", html: "<p>test</p>"
}).then(i => console.log("Sent:", i.messageId))
.catch(e => console.log("Error:", e.message));
SCRIPT
cat /tmp/smtp-test.js | docker exec -i nodebb node
```

如果 nodemailer 测试成功但 NodeBB 发不出 → 检查 `email:smtpTransport:enabled` 是否为 `1`。

## App Password 失效

Gmail App Password 是 16 位字母，中间带空格。静默失效的唯一症状是 530 错误。

**修复流程：**
1. 去 https://myaccount.google.com/apppasswords 重新生成
2. 更新 Redis：
   ```bash
   docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:auth:pass' 'new-password'
   docker compose restart nodebb
   ```
3. 不要删数据库——改个密码的事。

## enabled 开关被忽略

检查 Redis 中 `email:smtpTransport:enabled` 是否为 `1`（字符串）：
```bash
docker exec nodebb-redis redis-cli HGET config 'email:smtpTransport:enabled'
```
如果为空或 `0`：
```bash
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
docker compose restart nodebb
```

## 完整配置检查

```bash
docker exec nodebb-redis redis-cli HMGET config \\
  'email:smtpTransport:host' 'email:smtpTransport:port' \\
  'email:smtpTransport:secure' 'email:smtpTransport:auth:user' \\
  'email:smtpTransport:auth:pass' 'email:smtpTransport:enabled' 'email:from'
```

应返回：
```
smtp.gmail.com
465
true
ianlee168@gmail.com
<16-char-password>
1
tthbbs <ianlee168@gmail.com>
```
