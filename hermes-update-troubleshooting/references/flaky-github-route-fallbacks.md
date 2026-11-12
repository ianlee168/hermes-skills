# Flaky route to GitHub: triage, fallbacks, post-update state

Depth for failure mode 9 of the parent skill. Read this when an update stalls at
`→ Fetching updates...` on a machine whose `http.sslBackend` fix is already applied.

## 1. Which of the two timeouts fired

| evidence | layer | what it means |
|---|---|---|
| `✗ Failed to fetch updates from origin.` + `git fetch timed out after 300s` | updater's own `NETWORK_GIT_TIMEOUT_SECONDS = 300` on `_git_run(..., network=True)` | the guarded git call RETURNED — the timeout is real and reported |
| `step stalled: no stdout/stderr for 600s … cancelling its process tree`, exit `124`, update.log's last line still `→ Fetching updates...` | outer hand-off launcher idle watchdog | the guarded call never returned — git's lazy promisor grandchildren hold the captured pipes, so **no updater-level error will ever appear**. Do not wait for one; measure the network. |

Exit `124` means the watchdog, not a fetch bug. Both layers firing in the same
session just means the route is bad enough to stall either way.

## 2. Backend or route? Measure before theorizing

```bash
R=~/AppData/Local/hermes/hermes-agent
git -C "$R" config --show-origin --get-all http.sslBackend     # is the openssl fix still applied?
for be in schannel openssl; do for i in 1 2; do
  S=$(date +%s%N); timeout 60 git -C "$R" -c http.sslBackend=$be ls-remote --exit-code origin main >/dev/null 2>&1
  echo "$be #$i $(( ($(date +%s%N)-S)/1000000 ))ms exit=$?"; done; done
```

- openssl ≪ schannel → backend problem: keep `http.sslBackend=openssl` (mode 9 root cause).
- **both backends slow in the same session → the ROUTE is degraded; the backend is not
the cause and no config write will fix it.** (Observed: schannel 60 s/timeout vs openssl
50 s/16 s, where yesterday openssl was a steady 1.3 s.)
- Bimodal results for the identical request (1.8 s / 9 s / 22 s / 47 s / 60 s timeout) =
packet loss with TCP retransmit backoff, not bandwidth. One-line proof that the machine's
connectivity is fine and only git's HTTPS session suffers:
`curl -sS -o /dev/null -w '%{time_namelookup} %{time_connect} %{time_appconnect} %{time_total}' https://github.com/`
answering in ~0.2 s while git needs 30-70 s. `GIT_TRACE_CURL=1` shows the mechanism:
7-21 s gaps between `=> Send SSL data` and `<= Recv SSL data`.
- Volume is not the problem. A few hundred commits arrive as a few ~600 KB packs;
`http.version=HTTP/1.1` vs `HTTP/2` changes nothing; both are latency/round-trip bound.
- A treeless install amplifies it: `git diff --name-only HEAD origin/main` (trees only,
no blobs) can take ~180 s on a bad route — that is the checkout materialisation the
updater will repeat silently after its fetch, inside the same silent window.

## 3. Fallback that works: rewrite the GitHub remote through a mirror

Repo-local config write, one command to undo:
```bash
git -C "$R" config url."https://gh-proxy.com/https://github.com/".insteadOf "https://github.com/"
```
Verified shape: `ls-remote` drops from tens of seconds to ~1.5 s and the desktop-driven
update then completes normally (`→ Found N new commit(s)` immediately after the mirror
line in update.log).

**Prove the mirror cannot feed wrong code** before trusting it — compare its ref against
an independently fetched official value:
```bash
BASE=$(curl -sS https://api.github.com/repos/<owner>/<repo>/commits/main \
        | python -c "import sys,json;print(json.load(sys.stdin)['sha'])")
git -C "$R" ls-remote --heads origin main | awk '{print $1}'      # must equal $BASE
```
Re-read `BASE` at compare time — an active repo moves within minutes, and a mismatch is
far more often your cached baseline than a lying mirror. (git still verifies every object
hash; the ref check guards against a mirror that serves a *different* ref.)

Notes and traps:
- Most CN mirrors in circulation are dead or broken (certificate subject mismatch,
connection refused, or intermittent `fatal: expected flush after ref listing`). Test ref
equality per candidate; a proxy that works most of the time can still truncate one
response.
- Undo: `git -C "$R" config --unset url."https://gh-proxy.com/https://github.com/".insteadOf`
- Disclose both side effects to the user:
  - the updater now prints `⚠ Updating from fork: <mirror url>` +
    "Your fork is not tracking the official Hermes repository … Skipping upstream setup"
    — cosmetic; the SHA equality above is the guarantee.
  - `insteadOf` has no fetch-only scoping, so pushes are rewritten too; set
    `git -C "$R" remote set-url --push origin https://github.com/<owner>/<repo>.git`
    if anything pushes from this checkout.

## 4. After the code moves: four states to check separately

`✓ Update complete!` is not the end of the story — each of these fails independently and
only one of them needs the user to act.

1. **Gateway alive.** Any failed or aborted run leaves it paused
(`gateway_state.json` → `"gateway_state": "stopped"`, `restart_requested: true`).
`hermes gateway status` must print `✓ Gateway process running (PID: …)`; restore through
the Scheduled Task, not `hermes gateway start` from an agent shell.
2. **Stale failure flag.** `.update_exit_code` is written when a *partial* step fails
(classically `⟲ Stopping 1 dashboard process(es) …` then
`⚠ … could not be auto-restarted`) and is what the desktop app reads to keep showing
"update failed". Only a later fully-successful gateway-mode completion rewrites it;
`behind: 0` does not clear it. Judge by `logs/update_receipts/latest.json` +
`git rev-list --count HEAD..origin/main`, never by this byte.
3. **Desktop app freshness.** The updater skips the desktop rebuild whenever the app is
running ("Windows locks a running app's files"), so the shell keeps its old `app.asar`
while the checkout is current. Prove staleness with counts, not by feel:
```bash
date -r "$R/apps/desktop/release/win-unpacked/Hermes.exe"                        # build time
git -C "$R" log -1 --format='%H %ad' -- apps/desktop                            # newest touch
git -C "$R" diff --name-only <build-sha> origin/main -- apps/desktop | wc -l    # >0 = stale
```
Remedy is a user action: quit Hermes Desktop, then update (the rebuild happens only when
the app is closed), then reopen — or Settings → About → Update now.
4. **Desktop backend.** The updater may stop the app's `serve` backend (it counts as a
"dashboard process") and fail to restart it, leaving a working UI against no backend.
Cheapest check: the port it serves on answers —
`curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8799/` → `200`.

Reading-order trap: `desktop-update-handoff.log` replays the launcher's watchdog line
into the update output, so `step stalled` can appear ABOVE the update lines it belongs to.
Read timestamps, not line order.

## 5. Unattended completion when the app must be closed to rebuild

When the user will not sit and re-click, hand the whole thing to a detached job:

- poll `tasklist` for `^Hermes.exe` until it disappears, with a bounded window (~30 min)
  — match case-sensitively, the CLI's lowercase `hermes.exe` is a false positive;
- then update from the checkout: `hermes update --yes --gateway --branch main --keep-stash`,
  retry once on non-zero;
- re-check `hermes gateway status`, `HEAD` vs `origin/main` and `.update_exit_code`;
- relaunch detached: `cmd //c start "" "<checkout>\apps\desktop\release\win-unpacked\Hermes.exe"`.

Start that job with `persist_on_release` — closing the desktop app can take the agent's
own session with it, and an unpinned job would die before it finished the update.
Tell the user the log path and that the window is bounded, so an abandoned run is
obviously a no-op rather than a mystery.
