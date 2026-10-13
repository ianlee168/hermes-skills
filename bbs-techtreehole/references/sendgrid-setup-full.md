# SendGrid SMTP Setup for NodeBB — Full Guide

## Why Not Gmail

Gmail App Passwords get randomly revoked by Google's "unusual activity" detection —
even from the same IP, same device, low usage. This causes `530-5.7.0 Authentication Required`
errors that appear to be SMTP config issues but are actually Google-side blocks.

SendGrid free plan (100 emails/month) is sufficient for a private forum.
API Keys don't get randomly revoked like Gmail App Passwords.

## Prerequisites

1. Register at https://signup.sendgrid.com
2. **Settings → Sender Authentication → Verify a Single Sender**
   - Add the sender email (e.g. `ianlee168@techtreehole.com`)
   - Check verification email and click the confirmation link
   - ⚠️ Status must be "verified" before SMTP will work
3. **Settings → API Keys → Create API Key**
   - Name: anything (e.g. `tthbbs-smtp`)
   - **Permission: Full Access** (Restricted Access causes 535 auth failure)
   - Copy the 70+ character key immediately

## SMTP Parameters

| Parameter | Value |
|-----------|-------|
| Host | `smtp.sendgrid.net` |
| Port | `587` |
| Security | STARTTLS (`secure: false`) |
| Username | **`apikey`** — literally the string "apikey", not your email |
| Password | The API Key from step 3 |

## NodeBB 4.12 SMTP Config (Redis)

NodeBB reads SMTP config from the Redis `config` hash, NOT from MongoDB `objects`.

### Critical: All Three Keys

1. **`email:smtpTransport:enabled = 1`** — without this, NodeBB falls back to sendmail
2. **`email:smtpTransport:service = nodebb-custom-smtp`** — without this, emailer.js won't read host/port (line 139 in `/usr/src/app/src/emailer.js`)
3. **`email:smtpTransport:user` / `email:smtpTransport:pass`** — NOT `auth:user`/`auth:pass`

```bash
# Complete SendGrid SMTP config
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:host' smtp.sendgrid.net
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:port' 587
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:secure' false
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:user' apikey
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:pass' 'SG.your_full_key'
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:service' 'nodebb-custom-smtp'
docker exec nodebb-redis redis-cli HSET config 'email:from' 'ianlee168@techtreehole.com'

# Then restart
docker compose restart nodebb
```

### API Key Safe Write (Avoid SSH Truncation)

The 70+ character key contains special chars. Shell heredocs and echo can truncate it.

**Safest method — pipe from file:**
```bash
# Write the key to a file first, then pipe to redis-cli -x
echo 'SG.your_70_character_key_here' | \
  ssh root@192.168.50.1 \
  'docker exec -i nodebb-redis redis-cli -x HSET config "email:smtpTransport:pass"'

# Verify full length was stored
ssh root@192.168.50.1 \
  'docker exec nodebb-redis redis-cli HGET config "email:smtpTransport:pass" | wc -c'
# Should return 71 (70 chars + newline)
```

## Verify SMTP Works

Test directly from within the container (bypasses NodeBB's email system):

```bash
cat > /tmp/test-sg.js << 'SCRIPT'
const nodemailer = require("nodemailer");
const t = nodemailer.createTransport({
  host: "smtp.sendgrid.net", port: 587, secure: false,
  auth: { user: "apikey", pass: "SG.your_key_here" }
});
t.sendMail({
  from: "ianlee168@techtreehole.com",
  to: "ianlee168@gmail.com",
  subject: "SendGrid Test",
  html: "<p>test</p>"
}).then(i => console.log("Sent:", i.messageId))
.catch(e => console.log("Error:", e.message));
SCRIPT

cat /tmp/test-sg.js | ssh root@192.168.50.1 'docker exec -i nodebb node'
```

## Testing Actual Registration Email

The NodeBB admin email test button sometimes fails even when real emails work.
Test by registering a new user on the forum.

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `535 Authentication failed: The provided authorization grant is invalid, expired, or revoked` | API Key not Full Access, or sender not verified | 1. Check Sender Authentication verified 2. Recreate API Key with Full Access 3. Wait a few minutes for propagation |
| `connect ECONNREFUSED 127.0.0.1:587` | `email:smtpTransport:service` not set to `nodebb-custom-smtp` | `docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:service' 'nodebb-custom-smtp'` |
| Backend test fails but direct nodemailer works | NodeBB admin test button uses different code path | Ignore test button; verify via new user registration |
| Email page shows Gmail config | MongoDB still has old data | Update MongoDB objects config with mongosh |
