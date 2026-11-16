# Removing an app/service installed inside WSL (Ubuntu on 50.110)

Teardown recipe validated 2026-09-06 removing openclaw (node gateway,
port 18789, registered in BOTH ianlee168's and root's systemd --user).
Use for "uninstall / 删了 / clean up <app> in WSL" tasks.

## Order of operations

1. **Inventory what exists** (don't guess — the user's nickname may
   not match any path):
   - `wsl.exe -l -v | tr -d '\0'` (WSL output is UTF-16; strip nulls)
   - inside the distro: `ps aux | grep -i <app>`; `ls -d ~/.<app>`
     `/root/.<app>`; units in `~/.config/systemd/user/` AND
     `/root/.config/systemd/user/`; `npm ls -g --depth=0`;
     `ls /usr/lib/node_modules/`
2. **Stop + disable the unit in EVERY user systemd instance** —
   systemd --user is per-login-user, and WSL commonly has both the
   normal user's and root's running. A service left enabled in the
   other instance comes straight back:
   ```
   wsl.exe -d Ubuntu-24.04 -- bash -lc 'systemctl --user stop X; systemctl --user disable X'
   wsl.exe -d Ubuntu-24.04 -u root -- bash -lc 'systemctl --user stop X; systemctl --user disable X'
   ```
   `disable` prints `Removed ".../default.target.wants/X"` — that
   confirms the autostart link is gone.
3. **Kill leftover process by PID** (from `ps aux`) — never `pkill
   -f <app>` whose pattern text sits in your own `bash -lc` command
   line; it matches the wrapper shell and kills the script mid-run.
4. **mv to backup, never rm** (user red line: undo plan shown
   first, explicit consent per call). Fixed literal suffix — `$()`
   date substitution is unreliable through `wsl bash -lc`:
   - user data `~/.<app>` → `~/.<app>.bak-<fixed-date>`
   - user unit file → same pattern
   - root data + root unit (via `-u root`) → collect under
     `/opt/<app>-backup-<fixed-date>/` — do NOT leave the renamed
     package dir inside `/usr/lib/node_modules` (npm dir-scan then
     reports it as installed: `openclaw.bak-@npm:openclaw@...`);
     also move the `/usr/bin/<app>` symlink there
   - app SSH keys `~/.ssh/id_*_<app>*` → into the backup dir; warn
     the user to revoke the pubkey at any remote it was registered
5. **Verify**: no process, no enabled unit in either user manager
   (`systemctl --user list-unit-files` under both users), `npm ls
   -g` clean, `ps aux | grep -i <app>` empty.
6. **Stray-file scan traps**: a whole-disk `find -iname '*<app>*'`
   will surface lookalike components of OTHER software (e.g.
   Hermes's own `openclaw-migration` skill/docs/tests, gbrain
   compat layers, clawhub schema files) — those are legitimate,
   never touch them. Only app-owned artifacts (its data dir, its
   unit, its npm package, its SSH keys) get moved.

## Restore (undo)

Move each `.bak-*` back to its original path, then
`systemctl --user enable X && systemctl --user start X` in the user
manager that owned it.
