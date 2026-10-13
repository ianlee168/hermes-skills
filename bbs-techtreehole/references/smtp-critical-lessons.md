# SMTP Configuration Critical Lessons (2026-05-29)

## Lesson 1: `email:smtpTransport:enabled` MUST be set to 1

NodeBB **does not enable SMTP by default**. Without `email:smtpTransport:enabled = 1`,
it falls back to sendmail (which doesn't exist in the container). You can set all
host/port/auth values perfectly and still no email will be sent.

**Fix in redis:**
```bash
docker exec nodebb-redis redis-cli HSET config 'email:smtpTransport:enabled' 1
```

## Lesson 2: MongoDB Nested Object Trap

**NEVER write a nested JSON object** to MongoDB under `email:smtpTransport`:

❌ WRONG:
```javascript
{ $set: { "email:smtpTransport": { host: "smtp.gmail.com", port: 465 } } }
```

This corrupts the config document — NodeBB reads `email:smtpTransport` and gets
an object instead of individual `email:smtpTransport:host` keys. The MongoDB
driver then times out on every read, making future MongoDB operations hang.

✅ CORRECT:
```javascript
{ $set: { "email:smtpTransport:host": "smtp.gmail.com" } }
```

## Lesson 3: Gmail is unreliable for forum email

Gmail App Passwords get randomly revoked by Google's security heuristics.
Even with:
- Same IP every time
- Low sending frequency  
- Correct App Password

Google will occasionally return `530-5.7.0 Authentication Required` and require
a new App Password to be generated.

**Use SendGrid (or similar transactional email service) instead.**

## Lesson 4: API Key with special chars gets truncated in SSH

Tokens containing `$`, `{`, `}` get interpreted by bash when passed through SSH.
```bash
# WRONG - truncated:
ssh root@nas 'docker exec nodebb-redis redis-cli HSET config pass "SG.xxx${yyy}..."' 

# RIGHT:
echo 'SG.xxx...' | ssh root@nas 'docker exec -i nodebb-redis redis-cli -x HSET config "email:smtpTransport:auth:pass"'
```
