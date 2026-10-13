# Gmail SMTP Setup for NodeBB

## Prerequisites

1. Enable 2-Step Verification on Google Account
2. Generate App Password at https://myaccount.google.com/apppasswords
3. Select "Mail" as app and name it (e.g. "NodeBB")

## Limits

- **500 emails/day** (free tier)
- App Password is 16 characters, format: `xxxx xxxx xxxx xxxx`

## Configuration via Redis

NodeBB 4.x stores email settings in the `config` hash in Redis:

```bash
docker exec nodebb-redis redis-cli HSET config email:smtp:host smtp.gmail.com
docker exec nodebb-redis redis-cli HSET config email:smtp:port 465
docker exec nodebb-redis redis-cli HSET config email:smtp:secure true
docker exec nodebb-redis redis-cli HSET config 'email:smtp:auth:user' your@gmail.com
docker exec nodebb-redis redis-cli HSET config 'email:smtp:auth:pass' 'your-16-char-app-password'
docker exec nodebb-redis redis-cli HSET config email:from your@gmail.com
docker compose restart nodebb
```

**Note**: The admin UI at `/admin/settings/email` may show empty fields even after Redis config is set. The config still works.

## Test SMTP directly

Use nodemailer inside nodebb container (bypasses NodeBB's mailer):

```bash
cat > /tmp/nbb-test-smtp.js << 'SCRIPT'
const nodemailer = require("nodemailer");
const transporter = nodemailer.createTransport({
  host: "smtp.gmail.com", port: 465, secure: true,
  auth: { user: "your@gmail.com", pass: "your-16-char-pass" }
});
transporter.sendMail({
  from: "your@gmail.com", to: "your@gmail.com",
  subject: "Test", html: "<p>test</p>"
}).then(info => console.log("Sent:", info.messageId))
.catch(err => console.log("Error:", err.message));
SCRIPT
cat /tmp/nbb-test-smtp.js | docker exec -i nodebb node
```

## Troubleshooting

- Check `/admin/settings/email` — if test email button returns "Forbidden", use nodemailer direct test instead
- Check Gmail Spam folder if emails are sent but not received
- App Passwords only work with 2FA enabled on the Google account
