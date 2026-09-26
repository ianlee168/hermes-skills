# Windows: the managed runtime vs the checkout venv (gateway import graft)

Read when a Windows gateway logs `ModuleNotFoundError: No module named
'pydantic_core._pydantic_core'`, when cron agent turns fail with
`Failed to initialize OpenAI client: …`, or when you are tempted to "fix" it by
changing the gateway's interpreter.

## Stop-loss options that do NOT touch the code tree

Upstream tracking: **#122183** (P1; PRs #122330/#122333 converging on a selected_venv/
ownership guard), **#122324**, dupes #122556/#122400/#122555. Add evidence as a COMMENT, not a
new issue. Evidence that lands well: the `hosted_room_worker died … No module named
'pydantic_core._pydantic_core'` loop with timestamps, both ABIs on disk (`cp311` in the
checkout venv vs `cp314` in the PM generation), and the cron-side symptom
`ERROR cron.scheduler: Job '<job>' failed: RuntimeError: Failed to initialize OpenAI client:
…` — that is the one users notice, and it hides because platforms stay connected.

### 1. Convert model-free cron jobs to `no_agent` scripts

`no_agent` short-circuits before the agent/client is ever constructed, so it is structurally
immune. Recipe plus the real-fire acceptance test (temporary schedule, confirm
`source=builtin`, then change the expression back and re-check `next_run_at`) live in skill
`hermes-cron-troubleshooting` → "agent 型作业撞上 gateway 环境损坏".

### 2. Rename the checkout venv (restores per-turn subprocesses too)

The graft's candidate list is `[$VIRTUAL_ENV (cleared by hermes_bootstrap, and popped again by
pm/environments.py), <checkout>/venv]` — so removing the only surviving candidate turns
`site.addsitedir()` into a no-op. Rename `<checkout>/venv` → `venv.disabled-<date>` and
restart the gateway: the PM generation stays first on `sys.path` *and* stays the
`PYTHONPATH`/`VIRTUAL_ENV` handed to children. That child-env rewrite is why the damage is
wider than the room worker — every per-turn subprocess (platform agent turns, A2A) inherits
the 3.11 site-packages first. Confirmed independently on a real install in #122183, where the
desktop app was unaffected because its backend runs `hermes\bin\hermes.exe serve` on the
store Python.

Before renaming, check what still points into that venv:

```bash
which -a hermes            # the PATH shim is often <checkout>/venv/Scripts/hermes
<HERMES_HOME>/bin/hermes.exe --version    # store-python entry, survives the rename
grep -rl "hermes-agent[\\/]venv" config.yaml cron/jobs.json scripts/ gateway-service/
```

On the install checked here the Scheduled-Task launcher was already the store Python (so the
gateway still starts) and `bin/hermes.exe` answered `--version` on 3.14, i.e. the CLI has a
fallback entry. Unknown before you try it: whether `hermes update` still provisions cleanly
with the legacy venv absent. Undo = rename back + one gateway restart. After the restart
`hermes gateway status` may still print "No gateway process detected" — that is failure mode 7
(matcher blindness), not a failed start: judge by `gateway_state.json` and a fresh heartbeat.

### 3. What the rename looked like when actually applied (2026-09-26, this install)

Order that worked: `Stop-Process -Id <pid from gateway_state.json>` → rename
`<checkout>/venv` → `venv.disabled-<date>` → `schtasks /Run /TN Hermes_Gateway`.

```text
after restart, running the startup repro with the venv gone:
  _ensure_windows_gateway_venv_imports(): sys.path delta = 0
  import pydantic/pydantic_core/openai: OK (pydantic 2.13.4, loaded from the PM env)
gateway.log: 2 platform(s) connected, turn machinery warmed, no hosted_room_worker death
             (previously it died 5× within seconds of every start)
errors.log:  0 pydantic errors after the restart
```

Two operational gotchas from that run:

- **`hermes gateway stop` cannot kill a gateway that discovery already lost.** Both plain stop
  and `stop --all` printed success ("Stopped 1 gateway process(es) across all profiles") while
  the real serving pid kept heartbeating — the stop path uses the same blind discovery as
  `status`. Read the pid out of `gateway_state.json` and terminate that process directly.
- **The PATH `hermes` shim falls through cleanly.** With `<checkout>/venv/Scripts/hermes` gone,
  `hermes` resolves to the PM-environment shim (`installs/<id>/environments/<gen>/venv/Scripts/hermes`),
  and `<HERMES_HOME>/bin/hermes.exe` also works — both report Python 3.14 and the current version,
  so the CLI needs no PATH surgery.

## The three Python homes (do not conflate them)

| Purpose | Path | Version |
|---|---|---|
| PM "store" tool python — what the gateway/desktop/`serve` actually run on | `%LOCALAPPDATA%\hermes\tools\python-<ver>-…\python.exe` | e.g. 3.14 |
| Dependency environment for that store python | `%LOCALAPPDATA%\hermes\installs\<install-hash>\environments\<env-hash>\venv` | same major.minor as the store python |
| Checkout venv — the `hermes` CLI's own env, re-homed through a private runtime | `hermes-agent\venv` → `hermes-agent\.hermes-runtime\python\generation-*\cpython-<ver>-…` | e.g. 3.11 |

`hermes_bootstrap` resolves the store python's dependency environment and puts its
`Lib\site-packages` on `sys.path` — that env DOES contain correctly-built extensions
for its own interpreter (pydantic, aiohttp, jiter, openai, numpy, …). The checkout
venv is a second, version-skewed tree used by the CLI; on this install it predates the
managed runtime and holds ~30 **cp311-only** extension packages.

## Mechanism

`gateway/run.py::_ensure_windows_gateway_venv_imports()` runs during `start_gateway`,
iterates `[$VIRTUAL_ENV, <checkout>/venv]`, and for the first candidate whose
`Lib\site-packages` exists does `site.addsitedir(...)` then `sys.path.insert(0|1, ...)`.
`hermes_bootstrap` clears `VIRTUAL_ENV` before that point, so the only surviving
candidate is the checkout venv — inserted AHEAD of the managed env. Pure-Python imports
still resolve; every compiled extension then fails to load, and the failure is reported
as `ModuleNotFoundError` (the finder skips a `.pyd` whose ABI tag does not match).

## Repro (all read-only)

```bash
cd ~/AppData/Local/hermes/hermes-agent

# 1. the ABI mismatch: two core extensions, two tags
ls venv/Lib/site-packages/pydantic_core/*.pyd
ls ../installs/*/environments/*/venv/Lib/site-packages/pydantic_core/*.pyd

# 2. bootstrap clears VIRTUAL_ENV (that is why the checkout venv always wins)
./venv/Scripts/python.exe -c "import os,sys;os.environ['VIRTUAL_ENV']=r'C:\x';import sys;sys.path.insert(0,r'C:\Users\<user>\AppData\Local\hermes\hermes-agent');import hermes_bootstrap;print('VE after bootstrap =',os.environ.get('VIRTUAL_ENV'))"

# 3. the graft, called exactly as startup calls it, then the failing import
./venv/Scripts/python.exe -c "import sys;sys.path.insert(0,r'C:\Users\<user>\AppData\Local\hermes\hermes-agent');import hermes_bootstrap;from gateway.run import _ensure_windows_gateway_venv_imports as f;f();print(sys.path[:2]);import pydantic"
```

## Process-tree probe (the step that settles "which interpreter is really serving")

```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*gateway run*' } | Select-Object ProcessId,ParentProcessId,CreationDate,ExecutablePath,CommandLine | Format-List"
```
A stock Windows Scheduled-Task start looks like `wscript → <store python> -m hermes_cli.main
gateway run` — one process, visible to `hermes gateway status`. An extra
`-I -c "…runpy.run_module('hermes_cli.main')"` child means the gateway re-execs itself onto
the managed python: that child is the real serving process (it holds `gateway.lock` and
writes `gateway_state.json`), and it is the one whose imports fail.

## Interpretation

- Room worker / cron agent turns fail, but weixin, Home Assistant and other platform
  adapters stay `connected` — the graft only bites imports that pull compiled wheels, and
  the agent stack does (pydantic → pydantic_core; `openai` → `jiter`).
- `hermes gateway status` can therefore be `✓ running` while agent work is broken: treat
  `gateway.log` + a cron job's `Last run: … error:` line as the health signal, not the
  status card.
- Same wrapper form is why the updater's own post-update verify can conclude "no stable
  gateway process appeared" and end the run with exit 1 although the code landed.

## Fix shape (upstream)

`_ensure_windows_gateway_venv_imports` should either prefer the environment
`hermes_bootstrap` already resolved, or skip any candidate whose compiled extensions do not
match `sys.version_info` (e.g. compare against the venv's `pyvenv.cfg` `version`). A patch
applied inside the checkout is NOT durable here: the next `hermes update` autostashes
local changes, so it evaporates — report upstream instead of patching in place.
