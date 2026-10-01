---
name: cloudflare-cf-cli
description: Use when installing or driving Cloudflare's cf CLI.
version: 1.0.0
author: 110妹 (50.110)
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [cloudflare, cf-cli, workers, d1, deploy, npm, agentic-cli]
    triggers: ["装 cf", "cloudflare cli", "cf deploy", "cf dev", "cf init",
               "cf auth", "workers runtime crashed", "npm install-scripts",
               "workerd postinstall", "部署到 cloudflare", "cloudflare 3000 api"]
    related_skills: [cloudflare-workers-d1, hermes-windows-bash-quirks]
---

## When to Use

- The user says "装 cf" / "Cloudflare CLI" / "cf deploy" / "部署到 Cloudflare".
- A Worker deploy or `cf dev` fails, or a `cf` command returns `10000 Authentication error`.
- Managing Cloudflare from the command line instead of the dashboard.

# Cloudflare `cf` CLI

`cf` is Cloudflare's agentic CLI: every Cloudflare product, ~3000 operations,
JSON by default, plus `cf cli search "<intent>"` so an agent can find the right
command without loading thousands of `--help` texts. It is the successor path
to Wrangler (Wrangler keeps working; `cf migrate` converts a Worker later).

Package identity check before installing: the npm name is literally `cf`, and
the legitimate one is maintained by `wrangler-publisher@cloudflare.com`
(`curl -s https://registry.npmjs.org/cf`). Version line is `1.0.0-beta.N`.

## Install

```bash
npm i -g cf
```

**The workerd allowed-scripts trap (npm ≥ 11).** npm blocks third-party
`postinstall` scripts by default, and `workerd` (the Workers runtime used by
the local dev server) is one of them. The install itself still "succeeds"; the
symptom shows up only in `cf dev`:

```
VITE vX ready in 1.2s
➜  Local:   http://localhost:5173/
The Workers runtime crashed unexpectedly and is being restarted (crash #1).
```

Fix inside the project (one-off, per project):

```bash
cd <project> && npm install-scripts approve workerd
npm install   # or npm rebuild workerd
```

After approval `cf dev` starts clean and `curl localhost:5173` returns the
Worker's response. (`npm i -g --allow-scripts=workerd cf` does NOT put a usable
workerd in the global tree — projects install their own runtime dependency, so
fix the project, not the global install.)

## Auth — env vars, not the browser

`cf auth login` is the OAuth/browser path. For an agent the reliable route is
the standard Cloudflare env vars, which `cf` reads as `authSource`
(`cf auth whoami` prints it):

```bash
source <creds-script>          # loads the values at runtime, prints only flags
cf auth whoami                 # {"authenticated":true,"tokenValid":true,...}
```

- `CLOUDFLARE_API_TOKEN` — the API token; `CLOUDFLARE_ACCOUNT_ID` — account id
  (zone-scoped commands also take `CLOUDFLARE_ZONE_ID` / `-z`).
- Account id can always be recovered from `~/.cloudflared/cert.pem`: strip the
  PEM markers, `base64 -d`, read `"accountID":"<32 hex>"`.
- Named profiles exist too: `cf auth create <name>` / `cf auth list` /
  `cf auth activate <name> [dir]` (binds a profile to a directory) /
  `cf auth delete`.
- Keep tokens out of the reply and out of command text — extract in the shell
  and pass the variable. Never print the value (this includes *.pem payloads:
  cloudflared's cert also carries an apiToken).

### Two Cloudflare tokens are not interchangeable

| Commands | Token |
|---|---|
| workers / deploy / dns / account | Workers token |
| **everything D1** | the D1 token |

With the Workers token, `/accounts/<a>/d1/database` returns
`[10000] Authentication error · 401`. Run D1 commands with the D1 token:

```bash
CLOUDFLARE_API_TOKEN="$D1_TOKEN" cf d1 list
```

This is the same trap documented in `cloudflare-workers-d1`; put both tokens in
the creds script so you never have to guess.

## Verified flow (deploy a Worker end to end)

```bash
cf init workers <dir> --package-manager npm   # non-interactive runs MUST pass the dir
cd <dir>
cf deploy --message "first deploy"            # builds via vite, uploads, prints the URL
cf dev                                        # local: http://localhost:5173
```

- `cf init` on an empty dir scaffolds a hello-world Worker plus
  `cloudflare.config.ts` (TypeScript config, `bindings` helpers from `cf/config`)
  and `vite.config.ts`. On a non-empty dir it switches to autoconfig.
- Deploy output to quote back to the user: the `https://<worker>.<subdomain>.workers.dev`
  line and the version id. **Verify with a real request** —
  `curl -s -o /dev/null -w '%{http_code}' <url>` — a successful upload is not a
  serving Worker.
- `cf deploy --dry-run` builds without uploading; use it when the user only
  wants a build check (avoid creating resources on their account).
- Deploying and `cf dev` are free-tier safe; anything that provisions paid
  resources (plans, paid add-ons, buying a domain) is a monetary action —
  ask first, per this user's standing rule.

## Pitfalls

- **`timeout N cf dev` leaves the dev server alive.** `timeout` kills the `cf`
  wrapper; the `npx vite` child keeps LISTENING on 5173. Cleanup: check
  `netstat -ano | grep 5173`, confirm the PID is the vite process
  (`Get-CimInstance Win32_Process -Filter 'ProcessId=<pid>'`), then
  `Stop-Process -Id <pid> -Force` as a single-purpose command. Never bundle a
  kill into a command that also pushes/verifies files.
- Write test projects and logs on a non-system drive (host convention:
  `D:\hermes-test\`) — never next to the CLI install or on C:.
- `cf cli search "<intent>"` is the right first move on an unfamiliar product —
  it returns `{command, summary}` pairs without burning context on `--help`.
- `cf auth whoami` also proves which account a token belongs to; check it before
  blaming the CLI for a 401.

## References

- `cloudflare-workers-d1` — the account's Workers/D1 triage playbook, token
  inventory, and the D1 quota fix ladder.
- Notes + creds script layout for this host: gbrain `tools/cloudflare-cf-cli`.
