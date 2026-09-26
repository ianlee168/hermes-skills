---
name: hermes-update-troubleshooting
description: Use when Hermes update fails but CLI update works.
category: software-development
---

# Hermes Agent Self-Update Troubleshooting

On Windows, Hermes updates from the desktop app or `hermes update` both
mutate the same checkout at `%LOCALAPPDATA%\hermes\hermes-agent`.
Update evidence lives in (all under `%LOCALAPPDATA%\hermes\`):

- `logs\update.log` — full transcript; every CLI/`hermes update` run opens
  with `=== hermes update started <ts> ===`
- `logs\desktop.log` — the **desktop app's own preflight**, which runs
  *before* the CLI updater starts; its `[updates] ...` lines are the only
  record of aborts that never reach update.log (see mode 6)
- `.update_check` — JSON `{"behind": N, "ver": ...}`
- `.update_exit_code` — last update exit code
- `logs\desktop-update-handoff.log` + `logs\update_receipts\` — hand-off
  relaunch lines and per-run receipts

**Map the user's report to a timestamped attempt before theorizing.**
"CLI 更新又失败了" does not pin the code path: if update.log has no run at
the time the user reports, the app's preflight aborted (mode 6) or nothing
ran — read `desktop.log` for that minute. `behind: 0` + exit code 0 means
the last update actually succeeded; the user may be seeing a stale failure.

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
[updates]   PID 5264  python.exe  ...\hermes-agent\venv\Scripts\python.exe C:\Users\<user>\ha-doorbell\doorbell_watch.py
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
uv venv --python "C:/Users/<user>/AppData/Local/Programs/Python/Python314/python.exe" .venv
uv pip install --python .venv/Scripts/python.exe websockets micloud pycryptodome requests
# start_watcher.vbs: py = base & "\.venv\Scripts\python.exe" (+ system-python fallbacks)
taskkill /PID <shim> /PID <child> /F
powershell -NoProfile -Command "Start-Process wscript.exe -ArgumentList '\"C:\Users\<user>\ha-doorbell\start_watcher.vbs\"'"
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

## Failure mode 6b: `git fetch timed out after 300s` (pure network, nothing local)

update.log shows `✗ Failed to fetch updates from origin.` +
`git fetch timed out after 300s with no response from the remote`, then the
gateway is restarted and the run ends exit 1 with the checkout UNCHANGED
(receipt `post_update.sha == pre_update.sha`, `exit_code: 1`,
`stop_reason: sys.exit(1)`). Nothing to repair — re-run the update; a direct
`git fetch --dry-run` in the checkout distinguishes a dead remote (fails too)
from a transient stall during the update (succeeds in ~1s).

## Failure mode 7: the relaunched gateway is invisible to Hermes's own matcher → every Windows update ends exit 1

Symptom: `✓ Update complete! (git.X → v.Y)` with code, TUI, web UI and desktop
all built, immediately followed by
`⚠ Windows gateway restart could not be verified — no stable gateway process
appeared after relaunch` / `✗ Windows gateway recovery failed`, exit 1, receipt
`outcome: "partial"` + `gateway_restart.incomplete: true`. The desktop app then
shows "更新失败" although the tree is current (`hermes update --check` →
*Already up to date*, `git status` clean).

Cause: the post-update restart spawns the gateway as an inline-source wrapper
(`<managed-python> -I -c "…runpy.run_module('hermes_cli.main', alter_sys=True)"
gateway run --replace`). `gateway.status._gateway_command_subcommand`
DELIBERATELY refuses `python -c <src>` (`inline_source_flag_index` → None, bug
class #107002), so `find_gateway_pids()` never sees that process. Prove it:

```bash
cd ~/AppData/Local/hermes/hermes-agent
./venv/Scripts/python.exe -c "
import psutil, subprocess
from gateway.status import looks_like_gateway_command_line as M
from hermes_cli.gateway import find_gateway_pids
for p in psutil.process_iter(['pid','cmdline']):
    c = p.info['cmdline'] or []
    if 'gateway' in ' '.join(c).lower():
        print(p.info['pid'], M(subprocess.list2cmdline(c)), c[:2], c[-3:])
print('find_gateway_pids:', find_gateway_pids())"
```

A live gateway printing `False` + `[]` is this mode. Consequences beyond the
false failure card: `hermes gateway status` says "✗ No gateway process
detected" while `gateway_state.json` is still heartbeating every minute, and
duplicate-launch protection is off (a second gateway can start and double-connect
the same bot token).

Same-run tell, no guessing required: the updater's fleet matrix is built from
`gateway_state.json` (`update_cmd_fleet.py`), so it prints
`✓ default (pid …) @ <new sha> — up to date` one line BEFORE the process-table poll
reports "no stable gateway process appeared". Two detectors, one process, opposite
answers = discovery bug, never a death (and never a Job Object: the pid keeps
heartbeating minutes later).

`gateway_spawn_intent_subcommand()` — the opposite-answer variant written for
spawn-intent callers — is blind to this launcher form too: it peels the `-c` wrapper
by scanning suffixes AFTER the source literal, and the only tokens there are
`gateway run --replace`, which then fail its own entrypoint pre-check
(`hermes_cli.main` / `hermes_cli/main.py` / basename `hermes[.exe]`) → `None`. So
`tests/_fixtures/live_system_guard.py` and anything else gating on spawn intent
shares the hole — worth mentioning in any report.

Upstream: **NousResearch/hermes-agent#123490** (also #122495; #123430 is a dupe).
Report by COMMENTING there with fresh probe output + the SHA you saw it on — the
Windows gateway bugs are already filed and duplicated reports get auto-labeled.

Fix (needs the user's explicit OK — it kills a live gateway): stop the tree, then
start through the Scheduled Task, which uses the detectable `-m hermes_cli.main` form:
```bash
hermes gateway stop                   # kills the whole tree (verified); `schtasks /End` does NOT
sleep 10; tasklist /FI "PID eq <pid>"  # confirm every PID of the tree is gone
schtasks /Run /TN Hermes_Gateway      # never `hermes gateway start` from an agent shell: Job Object (#91675)
sleep 30; hermes gateway status       # must print "✓ Gateway process running (PID: …)"
```
Verify the new one is detected AND imports its managed environment: fresh lines
in `logs/gateway.log` with no `ModuleNotFoundError: pydantic_core._pydantic_core`
(see mode 8), and `gateway_state.json` carrying a NEW pid + current `code_sha`.

Pitfall — act on the process TREE, not the PID that `status` prints: the gateway
re-execs itself into an inline-wrapper child (see mode 8), so the reported PID can be a
harmless parent while the child serves and holds `gateway.lock`/`gateway_state.json`.
Probe the tree before/after any stop:
```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*gateway run*' } | Select-Object ProcessId,ParentProcessId,ExecutablePath | Format-List"
```
`taskkill /F` and `hermes gateway stop` are both behind an approval gate. If the gate
returns *no answer* (timeout), the command did NOT run: stop the workflow and ask the
user in plain text — never retry, rephrase, or reach the same outcome another way.

## Failure mode 8: gateway grafted the checkout's 3.11 venv onto the managed 3.14 runtime (kills cron agent turns)

Symptom A — gateway log, 5× per start then give up:
`ERROR gateway.run: Supervised task hosted_room_worker died … ModuleNotFoundError:
No module named 'pydantic_core._pydantic_core'`, traceback importing pydantic from
`hermes-agent\venv\Lib\site-packages` (the cp311 build) while the process runs the
managed Python 3.14 (`tools/python-3.14.7+…\python.exe`).

Symptom B — the one that hurts: **every cron agent turn fails**, e.g.
`Last run: … error: RuntimeError: Failed to initialize OpenAI client: No module
named 'pydantic_core._pydantic_core'`. Messaging/platforms stay connected, so this
hides for a day.

Mechanism (NOT a startup race — it is unconditional):
`gateway/run.py::_ensure_windows_gateway_venv_imports()` (called during
`start_gateway`) does `site.addsitedir(<candidate>/Lib/site-packages)` for candidates
`[$VIRTUAL_ENV, <checkout>/venv]` and inserts the winner at `sys.path[0:2]`.
`hermes_bootstrap` CLEARS `VIRTUAL_ENV` before the gateway reaches that call, so the
only surviving candidate is `<checkout>/venv/Lib/site-packages` — a 3.11 env holding
~30 cp311-only extension packages (pydantic_core, jiter, aiohttp, tokenizers, psutil,
cv2, av, ctranslate2, …). Under the managed 3.14 interpreter every one of them is
unimportable, and because that dir is inserted FIRST it shadows the correct
`installs/<hash>/environments/<hash>/venv` that bootstrap already put on `sys.path`.
Prove the clear + the graft in one shot:
```bash
cd ~/AppData/Local/hermes/hermes-agent
./venv/Scripts/python.exe - <<'PY'   # shows the two envs and both .pyd ABI tags
import pathlib
for p in ('venv','../installs'):
    for f in pathlib.Path(p).rglob('_pydantic_core*.pyd'): print(f)
PY
./venv/Scripts/python.exe -c "import os,sys;os.environ['VIRTUAL_ENV']=r'C:\x';import sys;sys.path.insert(0,r'C:\Users\<user>\AppData\Local\hermes\hermes-agent');import hermes_bootstrap;print('VE after bootstrap =',os.environ.get('VIRTUAL_ENV'))"
# -> VE after bootstrap = None  (that is why the checkout venv always wins)
```

**Do NOT try to repair this by changing the launcher's interpreter — verified dead end.**
Editing `gateway-service\Hermes_Gateway.vbs` / `.cmd` to run the checkout venv python does
not change what serves: the gateway RE-EXECS itself onto the managed python through the same
inline wrapper, so the Scheduled Task's process tree becomes
`wscript → venv shim (3.11) → .hermes-runtime python (3.11) → <managed python> -I -c "…runpy.run_module('hermes_cli.main')"`.
The 3.11 parents show up in `hermes gateway status`, while the wrapper child is the process
that serves, holds `gateway.lock`/`gateway_state.json` and still dies of the graft — strictly
worse than stock, because a PID-based stop then targets a harmless parent. Revert such edits:
the launcher decides only the FIRST process, never the runtime.

Also do NOT copy cp314 `.pyd` files into the 3.11 venv: the clash surface is ~30 compiled
packages, and the 3.11 CLI legitimately uses that same site-packages tree.

Upstream: **#122183** (P1; PRs #122330/#122333 converging on a selected_venv/
ownership guard), **#122324** (P1), dupes #122556 / #122400 / #122555. Add evidence as
a COMMENT, not a new issue. Evidence that lands well: the 5×
`hosted_room_worker died … ModuleNotFoundError("No module named
'pydantic_core._pydantic_core'")` loop with timestamps, both ABIs on disk
(`<checkout>\venv\Lib\site-packages\pydantic_core\_pydantic_core.cp311-win_amd64.pyd`
vs `installs/<id>/environments/<gen>/venv/...\_pydantic_core.cp314-win_amd64.pyd`),
and the cron-side symptom
`ERROR cron.scheduler: Job '<job>' failed: RuntimeError: Failed to initialize
OpenAI client: No module named 'pydantic_core._pydantic_core'` — that is the one
users notice, and it is easy to miss because platforms stay connected.

Durable fix is upstream: `_ensure_windows_gateway_venv_imports` must skip a candidate venv
whose compiled extensions cannot load under `sys.version_info` (or simply trust the managed
environment `hermes_bootstrap` already put on `sys.path` rather than grafting at all). Until
that lands, treat it as an upstream bug: messaging and platforms keep working, **cron agent
turns fail**, and a locally patched tracked file is stashed away by the next
`hermes update --keep-stash` anyway.

Stop-loss without patching the tree: any cron job whose real work needs no model can be
converted to a `no_agent` script job, which short-circuits before the agent/client is
ever constructed and is therefore immune to this graft — recipe and the real-fire
acceptance test are in skill `hermes-cron-troubleshooting` ("agent 型作业撞上 gateway 环境损坏").

Depth — runtime layout, the three repro one-liners, and the process-tree probe:
`references/windows-gateway-runtime-graft.md`.

## Fix ladder (in order)

0. `grep -a "venv-blocked\|venv-blocker" %LOCALAPPDATA%\hermes\logs\desktop.log`
   → a *non-Hermes* script listed there is mode 6 (fix its launcher).
   When the user's story doesn't match the logs, read what they actually
   typed: `%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt`
   tail — `hermes update` retried next to `tasklist | findstr hermes` means
   they were fighting a blocker by hand (and looking for `hermes.exe` while
   the holder is `python.exe`).
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
- ❌ Do NOT open a new upstream issue before searching:
  `gh issue list --repo NousResearch/hermes-agent --search "<signature>" --state all`.
  Both Windows gateway bugs here (#123490, #122183) and the GBK decode crash
  (`UnicodeDecodeError: 'gbk' codec can't decode byte 0x94` in
  `subprocess._readerthread` → #122772) are already filed; posting a comment with a
  NEW SHA + measured probe output is the contribution, a duplicate is noise.
