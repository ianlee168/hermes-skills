# Hermes update self-lock deferral — deep dive (2026-08-15)

Verified on <WIN_HOST> (Windows 11, git-checkout install, venv at
`%LOCALAPPDATA%\hermes\hermes-agent\venv`). Full root-cause trace of the
"update has been deferred: the next `hermes` launch will complete it"
message.

## The deadlock

`hermes update` prints the deferral, pauses/restarts the gateway, exits 2.
Then `hermes version` still shows "N commits behind" forever. Re-running
`hermes update` reproduces the same deferral every time. The update can
NEVER complete on its own from this state.

## Root cause chain (verified with audit hooks)

1. `hermes_cli/main.py` top-level does `load_hermes_dotenv(...)` →
   imports `agent.secret_sources.registry` (frame: main.py:700).
2. `registry._ensure_builtin_sources()` imports
   `agent.secret_sources.bitwarden` (function-scoped import, but the
   function runs during registration).
3. `bitwarden.py` lines 50-52 do TOP-LEVEL `from cryptography.hazmat...
   import ...` → maps `cryptography._rust.pyd` into the process.
4. Result: ANY `hermes` CLI process (including `hermes update` itself)
   has the .pyd mapped. The self-lock preflight in update_cmd.py
   (`_detect_self_loaded_native_modules`, added 2026-08-10 in commit
   c6a71294b, issue #83569) therefore fires on EVERY run — deterministic,
   not random.

Detection probe:
```
venv/Scripts/python.exe -c "import sys, hermes_cli.main; print('cryptography.hazmat.bindings._rust' in sys.modules)"
```
→ True on broken checkouts.

## Why the deferral message is misleading

`_defer_update_for_self_lock` (update_cmd.py ~3075) writes the
`.update-incomplete` marker and exits BEFORE the git-pull section
(~4124). So:

- Code (git checkout) is NEVER updated by this path.
- The marker makes the NEXT non-update launch run
  `_recover_from_interrupted_install()` (main.py ~8038), which calls
  `run_core_install` (hermes_cli/_install_repair.py) — a full `.[all]`
  editable reinstall. Deps only, NO git pull. Then it clears the marker.
- Evidence it ran: `venv/Lib/site-packages/hermes_agent-*.dist-info`
  timestamp jumps to the gateway-restart time even though the checkout
  commit is unchanged.

## Upstream fix (what to pull in)

2026-08-15 01:55, a batch of commits breaks the loop by lazy-importing
secrets backends and deferring the registry import:

- 5a76c8a97 fix(update): lazy-import secrets backends + defer registry
  import — break Windows self-lock loop
- 3dc318687 fix(main): lazy-import secrets_cli to prevent
  cryptography._rust self-lock on Windows
- 230e5ff04 fix(main): revert secrets_cli to upstream, wrap registration
  in lazy closures
- 3f9150e5c fix(secrets_cli): defer bitwarden backend import to first
  attribute access
- a85a98110 test(lazy-secrets): CI compatibility

Check whether a checkout has them:
```
git merge-base --is-ancestor 5a76c8a97 HEAD && echo IN || echo NOT
```

## Verified fix

From an EXTERNAL terminal (agent terminal is blocked by the live-checkout
guard: "Blocked: `git pull` would rewrite Hermes's live source checkout"):

```
cd %LOCALAPPDATA%\hermes\hermes-agent
git pull --ff-only origin main
hermes update
```

After the pull, the lazy-import fix is present, `hermes update` passes the
self-lock preflight and completes normally. Verify with `hermes version`
(behind count) and `.update_check` (`behind: 0`).

## Markers & state files (so you don't misread the situation)

- `hermes-agent/.update-incomplete` — recovery breadcrumb (deferral
  writes it; recovery clears it after reinstall). Absent ≠ "no problem":
  it means deps were re-synced, code may still be stale.
- `hermes-agent/.update-incomplete.lock` — single-flight lock for
  recovery (stale after 1h).
- `%LOCALAPPDATA%\hermes\.update_check` — JSON `{"behind": N, ...}`.
- `%LOCALAPPDATA%\hermes\.update_exit_code` — last exit code; deferral
  exits 2 but this file may not be refreshed by every path.
- Gateway processes are `python.exe` — `tasklist | findstr hermes` finds
  nothing; use `tasklist | findstr python`.
