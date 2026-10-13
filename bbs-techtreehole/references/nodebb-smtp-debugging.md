# NodeBB 4.12 SMTP Debugging — How It Actually Works

## The Three-Key Problem

When SMTP is configured in Redis/MongoDB but emails don't send, check these three things IN ORDER:

### 1. `email:smtpTransport:enabled` MUST be `1`

Without this, NodeBB falls back to sendmail (which doesn't exist in Docker → silent failure, no error in logs). This is the #1 cause of "SMTP config looks right but nothing sends."

```bash
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
```

### 2. NodeBB 4.12 reads `email:smtpTransport:pass`, NOT `email:smtpTransport:auth:pass`

Source: `/usr/src/app/src/emailer.js` lines 129-145:

```javascript
const smtpOptions = { name: getHostname(), pool: config['email:smtpTransport:pool'] };
if (config['email:smtpTransport:user'] || config['email:smtpTransport:pass']) {
    smtpOptions.auth = {
        user: config['email:smtpTransport:user'],
        pass: config['email:smtpTransport:pass'],    // <-- NOT auth:pass
    };
}
```

So you need BOTH keys:
- `email:smtpTransport:user` = `apikey` (for SendGrid)
- `email:smtpTransport:pass` = actual API key

The `email:smtpTransport:auth:user` / `email:smtpTransport:auth:pass` keys are IGNORED by emailer.js.

### 3. `email:smtpTransport:service` must be `'nodebb-custom-smtp'` (or OMIT the key entirely)

If `service === 'nodebb-custom-smtp'`:
```javascript
smtpOptions.port = config['email:smtpTransport:port'];
smtpOptions.host = config['email:smtpTransport:host'];
```

If service is anything else (e.g. `'sendgrid'`, `'gmail'`):
→ NodeBB uses a built-in preset, ignores your host/port → connects to `127.0.0.1:587` → ECONNREFUSED

**Fix**: Either set `service` to `'nodebb-custom-smtp'` or don't set it at all (undefined also works).

## Complete Working Configuration

Redis config hash for SendGrid:

```bash
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:host' smtp.sendgrid.net
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:port' 587
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:secure' false
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:user' apikey
echo "SG.xxx..." | docker exec -i nodebb-redis redis-cli -x HSET config 'email:smtpTransport:pass'
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:service' 'nodebb-custom-smtp'
```

## Debugging Flow

1. **Test SMTP directly** (bypasses NodeBB entirely):
```bash
cat > /tmp/smtp-test.js << 'SCRIPT'
const nodemailer = require("nodemailer");
const t = nodemailer.createTransport({
  host: "smtp.sendgrid.net", port: 587, secure: false,
  auth: { user: "apikey", pass: "SG.xxx..." }
});
t.sendMail({
  from: "verified@domain.com",
  to: "you@gmail.com",
  subject: "Test", html: "<p>test</p>"
}).then(i => console.log("Sent:", i.messageId))
.catch(e => console.log("Error:", e.message));
SCRIPT
cat /tmp/smtp-test.js | docker exec -i nodebb node
```

2. **If direct test works but NodeBB doesn't send**: Problem is in how NodeBB reads config → check enabled/pass/service as above.

3. **If direct test fails with 535**: API key issue on the provider side (wrong permissions, unverified sender, newly created key not yet active).

## Common 535 Responses

| Error | Likely Cause |
|-------|-------------|
| `535 Authentication failed: Bad username / password` | Wrong `user` or `pass` value |
| `535 The provided authorization grant is invalid, expired, or revoked` | API key disabled at provider; or wrong key in config; or API key shell-truncated |
| `535 Authentication Required` (Gmail) | App Password revoked by Google (frequent, random) |

## WARNING: Don't Delete Database for SMTP Issues

SMTP config lives in Redis config hash + MongoDB objects collection. If emails don't send:

✅ **Do**: Fix the Redis key, restart nodebb container
✅ **Do**: Update the pass key via `echo ... | redis-cli -x`
❌ **NEVER**: `docker compose down -v`, `rm -rf /mnt/user/appdata/postgres`, or any data deletion

The SMTP pass key on Redis is trivial to fix. Deleting databases to "fix" SMTP is catastrophic.
