# Headless rclone Google Drive OAuth (Unraid server, no browser)

How to add a Google Drive remote to the Unraid box (`192.168.50.1`, rclone v1.72.0 at
`/usr/bin/rclone`, `~/.config/rclone/rclone.conf` was EMPTY) when the server has no
browser. Worked through 2026-08-06; session paused awaiting user's browser authorization.

## Verified prerequisites (all confirmed before starting)

- Server reaches Google directly: `curl -s -o /dev/null -w '%{http_code}' https://accounts.google.com` → 302 in ~0.6s. Domestic broadband works — no proxy needed.
- User's Google account has **5TB** Drive space → 287G backup fits at $0 cost.
- WSL on the Windows host (50.110) has rclone v1.60.1-DEV — older than the server's 1.72.0, but the token JSON it produces is version-agnostic, so the mismatch is fine.

## The flow (two processes)

### 1. On the server — start `rclone config` (interactive, pty)

Run via `ssh -t root@192.168.50.1 "rclone config"` with `pty=true` + `background=true`,
then drive it with `process(action=submit)` answering:

```
n                                   # new remote
name> gdrive
Storage> drive                      # type name, not list index
client_id>      <Enter>             # blank = rclone internal key (fine)
client_secret>  <Enter>
scope> 1                            # 1 = drive, full access (needed for 287G backups)
service_account_file> <Enter>
Edit advanced config? n
Use web browser to automatically authenticate? n   # headless — this is the key choice
```

At this point rclone prints: `rclone authorize "drive" "<base64 state>"` and prompts
`config_token>` — it is now WAITING. Do not close this session.

### 2. On the Windows host — `rclone authorize drive --auth-no-open-browser` in WSL

```bash
wsl -e bash -lc "rclone authorize drive --auth-no-open-browser"   # pty + background
```

Output: `NOTICE: Please go to the following link: http://127.0.0.1:53682/auth?state=...`
Hand that URL to the user to open in their Windows browser (WSL2 localhost forwarding
makes 127.0.0.1 reachable from Windows). User signs in with the account that has the
Drive space, clicks Allow. rclone then prints the token JSON — paste it into the
server session's `config_token>` prompt.

### 3. Finish on the server

```
Shared Drive? n → y (save) → q
```

Verify: `ssh root@192.168.50.1 "rclone lsd gdrive:"` shows the user's Drive roots.

## Pitfalls

- **Never pick "y" (auto browser) on the server step** — no browser there; the flow
  falls back to the authorize dance anyway, so choosing n up front skips a failed attempt.
- `dmidecode`-style facts don't apply here, but the token prompt (`config_token>`) is
  the headless-landing spot; the `rclone authorize "drive" "<state>"` hint printed there
  is just the equivalent local command — running it on ANY browser-equipped machine works.
- If user's browser can't reach 127.0.0.1:53682 (WSL2 forwarding off), the authorize
  URL is still capturable — but the token JSON is what matters, so keep the authorize
  process alive until it prints it.
- Upload 287G will take many hours on domestic upstream; start with the small payload
  first (`appdata/` 389M + `libvirt.img` 1G) to validate the remote, then the big VM disks.

## State at session end (2026-08-06)

- Server config session: `proc_c0fb4e7c7762` (waiting at `config_token>`)
- WSL authorize: `proc_6f19a68f3745` (waiting for browser callback)
- Auth URL given to user: `http://127.0.0.1:53682/auth?state=C2dIp-6Aowu59YlgSIjDGQ`
- Next step: user authorizes → paste token → verify `rclone lsd gdrive:` → upload.
