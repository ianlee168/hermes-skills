---
name: hermes-update-troubleshooting
description: Use when Hermes update fails but CLI update works.
category: software-development
---

# Hermes Agent Self-Update Troubleshooting

On Windows, Hermes updates from the desktop app or `hermes update` both
mutate the same checkout at `%LOCALAPPDATA%\hermes\hermes-agent`.
Update evidence is **always** in:

- `%LOCALAPPDATA%\hermes\logs\update.log` — full update transcript
- `%LOCALAPPDATA%\hermes\.update_check` — JSON `{"behind": N, "ver": ...}`
- `%LOCALAPPDATA%\hermes\.update_exit_code` — last update exit code

**Diagnose from update.log FIRST** — do not theorize. `behind: 0` +
exit code 0 means the last update actually succeeded; the user may be
seeing a stale failure.

## Failure mode 1: npm EBADENGINE (the "worked before, now fails" cause)

Hermes declares an npm engine range in its package.json, e.g.
`"npm": "<11.10.0 || >=12.0.0"`. Any npm version in the **forbidden gap**
(here: 11.10 ≤ npm < 12, e.g. 11.12.1) makes every `npm install` step
fail with EBADENGINE, which cascades into web-UI build failure and
"Update partially complete — Node.js dependencies for repo root did not
refresh". Code + Python deps update; the dashboard/TUI end up mixed.

Fix (one-time, do NOT fight Hermes's own npm management):
```powershell
npm install -g npm@12          # satisfies >=12.0.0
# or downgrade into the lower window:
npm install -g npm@11.9.0
```
Verify: `npm --version`. This is why the in-app update "used to work" —
the system npm was once in-range, then got bumped into the gap.

## Failure mode 2: interactive prompt the GUI can't answer

When the checkout has local modifications, `hermes update` auto-stashes
them and prints:
```
⚠ Local changes were stashed before updating.
Restore local changes now? [Y/n]
```
- **From a CLI terminal**: the user sees the prompt and answers → update
  proceeds → succeeds. This is exactly why "CLI 更新成功".
- **From the desktop app**: there is no stdin; the update appears stuck /
  dead / failed. The user's natural conclusion is "App 更新失败".

If the user reports "app fails, CLI works" — check update.log for this
prompt. The durable fix is to clear the local modifications so no stash
is needed (`git status` clean in the checkout), or tell the user to run
`hermes update` from a terminal when local changes exist.

## Failure mode 3: state.db locked (update while app is running)

The GUI/desktop keeps `state.db` open; an update that needs to migrate
databases retries and logs "The next `hermes update` will retry" / a
concurrent-update guard ("Another Hermes update is already running
(PID ...)"). Fix: fully quit Hermes (tray + all `Hermes` processes)
before updating, and never double-trigger an update.

## Failure mode 4: ZIP-fallback update wipes the desktop build (shortcut dead)

Symptom: desktop shortcut points at
`%LOCALAPPDATA%\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe`
but the file/dir is gone ("快捷方式打不开"); the update itself reported
success. Evidence trail in `%LOCALAPPDATA%\hermes\`:

- `.hermes-update-result.json` → `"message": "Update complete. Reopen
  Hermes to finish (it could not restart itself)."` `manual: true`
- `logs\desktop-update-handoff.log` tail → `desktop skipped` / no
  "relaunching desktop" line (earlier successful runs always have it)
- `logs\update.log` → "⚠ Git update failed ... → Falling back to ZIP
  download..." then "✓ Updated N items from ZIP"

Mechanism: on Windows, when `uv pip install` fails mid-update (usually
`PermissionError: another process is holding hermes.exe open`, os error
32), `hermes update` falls back to downloading a GitHub source ZIP and
replacing the checkout. That path preserves ONLY top-level
`venv/node_modules/.git/.env` — so gitignored build artifacts
(`apps/desktop/release/` incl. Hermes.exe, `apps/desktop/dist/`, and
`apps/desktop/node_modules`) get wiped. The retry then reports "desktop
skipped" (stamp check sees no source change) and never rebuilds, so the
launcher can't restart the app. Underlying trigger was hermes.exe being
held open — often a second `hermes` process/gateway still running.

Fix:
```powershell
hermes desktop --force-build --build-only
```
(~2-4 min; re-runs npm install + electron-builder, regenerates
`apps\desktop\release\win-unpacked\Hermes.exe`, shortcut works again.)
Plain `hermes desktop --build-only` (no `--force`) also rebuilds when
`release/` is missing — the stamp check only skips the build when the
artifacts already exist. Verified 2026-08-15: successful `--build-only`
rebuilt a 214 MB Hermes.exe; the app then launched (multi-process
Electron tree). Note the update flow may report exit 0 with the desktop
stage unbuilt (`desktop-update-handoff.log` shows "retry exit code: 0"
while `release/` is missing) — trust the filesystem, not the exit code.
Check nothing else is holding hermes.exe first (`Get-Process hermes`)
to avoid re-triggering the ZIP path on the next update.

## Failure mode 5: desktop-driven update reports FAILED (exit 8) although the update succeeded

Symptom: the app shows "更新失败 / failed verification, repair the
installation", while code, deps, desktop build and gateway all landed.
This is a **false negative in the post-update verify step**, not a
failed update.

Prove success before believing the card:
- `logs/update_receipts/update_<ts>.json` → `outcome: success`,
  `pre_update.sha` / `post_update.sha` both present
- `apps/desktop/release/win-unpacked/resources/install-stamp.json` →
  `commit` equals the receipt's `post_update.sha` (`dirty: false`)
- `gateway_state.json` → `code_sha` = same sha, `running: true`
- `logs/desktop-update-handoff.log` tail → `verify! RuntimeError: The
  updated Desktop executable is missing` followed by `exit 8`

Root cause: the hand-off verify step calls
`verify_windows_desktop_update(Path.cwd())`, but the Desktop spawns the
hand-off with `cwd: HERMES_HOME` (`apps/desktop/electron/main.ts`), so
verification looks for `apps\desktop\release\win-unpacked\Hermes.exe`
under HERMES_HOME and reports the exe missing even though it is intact.

Rule out everything else with a cwd-exact repro (same interpreter and
one-liner the script uses):
```bash
cd ~/AppData/Local/hermes/hermes-agent   # checkout root
./venv/Scripts/python.exe -c "import hermes_cli.main; from pathlib import Path; from hermes_cli.desktop_update_verify import verify_windows_desktop_update; verify_windows_desktop_update(Path.cwd()); print('VERIFY OK')"
# -> VERIFY OK, exit 0
cd ~/AppData/Local/hermes                # HERMES_HOME
# same command -> RuntimeError: The updated Desktop executable is missing
```
Passes from the checkout root + fails from any other cwd = this bug.

Timeline rule: the hand-off loads `scripts/desktop-update/windows.ps1`
from the checkout **as it exists when the hand-off starts**, so a run
that *pulls* the verify code still executes the old script. The false
exit 8 therefore first appears on the **next** desktop-driven update —
"worked yesterday, failed today with no local change" is expected.
Check with `git show <pre_update.sha>:scripts/desktop-update/windows.ps1
| grep -c verify_windows_desktop_update` (0 = old script).

What to do: nothing. Do NOT press repair and do NOT rebuild the app —
the packaged app is intact and relaunches fine. Desktop-driven updates
keep working (only the report is wrong); `hermes update` from a terminal
is unaffected because it resolves the tree from module location.
Do NOT patch `windows.ps1` locally: the hand-off runs
`hermes update --force --keep-stash`, so a dirty tracked file gets
stashed/overwritten and can flip the updater into its ZIP-fallback path.

Status: fixed upstream by pinning the hand-off process cwd to the install
root before any update child starts (`[Environment]::CurrentDirectory =
$InstallRoot`; `HermesUpdateJob.StartAssigned` passes a null
CreateProcess currentDirectory, so children inherit the process dir).
Because the hand-off runs the script loaded at hand-off start, the fix
only takes effect **one desktop-driven update later** — a failure right
after pulling it is expected, not a regression.

Verify the mechanism without running an update: chdir to the checkout,
spawn a child with **no** explicit cwd, run the verify one-liner → child
sees the checkout and prints `VERIFY OK`. Do NOT test it from
PowerShell (`&`, `cmd /c`, `Start-Process`): PowerShell passes its own
location as the child's working directory, so the test false-negatives
even with the fix in place. Use a non-PowerShell parent (python
`os.chdir` + `subprocess.run(..., cwd=None)`) to mirror
`CreateProcess(null)`.

## Failure mode 6: an unrelated user script on Hermes's interpreter blocks every update

Symptom: the app (or CLI) aborts with "Update aborted: another Hermes
process is using this installation." **`update.log` has nothing** — the
venv-blocker guard runs before the log stream opens. The evidence is in
`logs\desktop.log`:

```
[updates] venv-blocker scan reported 1 holder(s); re-scanning after settle (attempt 2/3)
[updates] venv-blocked: 1 process(es) hold the install
[updates] error: Update aborted: another Hermes process is using this installation.
[updates]   PID 5264  python.exe  ...\hermes-agent\venv\Scripts\python.exe <USER_HOME>\ha-doorbell\doorbell_watch.py
```

Any process whose interpreter is the Hermes venv **or**
`.hermes-runtime\python\generation-*\...` counts as a holder — including
long-lived user scripts started from the Startup folder. Killing the
process buys one update; the launcher respawns it at next logon, so fix
the launcher, not the symptom.

Fix: give the user script its own interpreter and point the launcher at it
(2026-09-13, doorbell watcher on 50.110):
```bash
cd ~/ha-doorbell
uv venv --python "%LOCALAPPDATA%\\Programs\\Python\\Python314\\python.exe" .venv
uv pip install --python .venv/Scripts/python.exe websockets micloud pycryptodome requests
# start_watcher.vbs: py = base & "\.venv\Scripts\python.exe" (+ system-python fallbacks)
taskkill /PID <shim> /PID <child> /F
powershell -NoProfile -Command "Start-Process wscript.exe -ArgumentList '\"<USER_HOME>\ha-doorbell\start_watcher.vbs\"'"
```
Notes: the venv `python.exe` shim + its `.hermes-runtime` child are ONE
logical process (two PIDs, kill both), and the guard reports only the shim.

Verify read-only, with the exact scan the updater's preflight consumes:
```bash
cd %LOCALAPPDATA%\hermes\hermes-agent
./venv/Scripts/python.exe hermes_cli/_scan_venv_blockers.py
# before: {"ok": true, "blocked": true, "processes": [the user script]}
# after:  {"ok": true, "blocked": false, "processes": [], "pausable_gateways": 2}
```
`blocked: false` means the install is free — update normally (from the app
while it runs; the app stops/relaunches its own `serve` backend).

## Fix ladder (in order)

0. `grep -a "venv-blocked\|venv-blocker" %LOCALAPPDATA%\hermes\logs\desktop.log`
   → a *non-Hermes* script listed there is mode 6 (fix its launcher).
1. Read `%LOCALAPPDATA%\hermes\logs\update.log` tail — identify which
   mode you're in (EBADENGINE / stash prompt / DB lock / actually OK).
2. `npm --version` → if in a forbidden gap, `npm install -g npm@12`.
3. `git -C %LOCALAPPDATA%\hermes\hermes-agent status --short` → if dirty,
   either clean it or expect the interactive prompt (use CLI, not app).
4. Make sure Hermes is fully quit, then run `hermes update` from a
   standalone PowerShell/cmd (not through the app, not through an
   agent terminal that the app spawns).
5. Verify with `.update_check` (`behind: 0`) + `tail update.log`
   ("✓ Update complete!").

## Pitfalls

- ❌ Do NOT report "update failed" from a single in-app click without
  reading update.log — `behind: 0` means it already succeeded.
- ❌ Do NOT try to patch the engine range in package.json; the project
  is repo-owned and the fix is upgrading the system npm.
- ❌ Do NOT assume the desktop app and CLI update identically — the
  stash-restore prompt is interactive and only the CLI can answer it.
- ❌ Do NOT treat an in-app "update failed / repair installation" card
  as proof of failure — verify-step false negatives exist (see mode 5);
  check receipt `outcome`, `install-stamp.json` and `gateway_state.json`
  before touching anything.
- ❌ Hermes only upgrades npm inside its own managed Node install; the
  system npm (`C:\Program Files\nodejs\npm.cmd`) is left alone — that's
  the one you must fix yourself.
- ❌ Do NOT conclude "Hermes's updater is broken" from a refused update:
  check `desktop.log` for `venv-blocked` — a leftover user script holding
  the interpreter (mode 6) is the usual cause, and it is invisible in
  `update.log`.
- The SQLite WAL-reset warning in update.log ("Hermes venv links SQLite
  ... has the WAL-reset bug → provisioning a private Python runtime")
  is auto-repaired by Hermes itself; no user action needed.
