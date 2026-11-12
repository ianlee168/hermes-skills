# finish-desktop-update.ps1 -- run a Hermes update AND rebuild the packaged desktop app
# while Hermes Desktop is closed, then relaunch it.
#
# Why a task and not a normal shell: the update must run while Hermes.exe is NOT running
# (Windows locks a running app's files, so an in-app run skips the packaged-app rebuild),
# and the agent driving it lives inside that app. Task Scheduler owns this process, so it
# survives the app exiting.
#
# Run it like this (one-shot task; delete it afterwards -- a ONCE task still fires at its ST):
#   schtasks /Create /TN Hermes_FinishDesktopUpdate /SC ONCE /ST 23:58 /F /TR "powershell -NoProfile -ExecutionPolicy Bypass -File D:\hermes-test\finish-desktop-update.ps1"
#   schtasks /Run /TN Hermes_FinishDesktopUpdate
#   schtasks /Query /TN Hermes_FinishDesktopUpdate /FO LIST        # LastTaskResult 0 = ok
#   schtasks /Delete /TN Hermes_FinishDesktopUpdate /F
#
# Keep this file ASCII-only: Windows PowerShell 5.1 reads a BOM-less file as ANSI and
# mangles non-ASCII characters in paths and log lines.

param(
    [string]$HermesHome  = "$env:LOCALAPPDATA\hermes",
    [string]$Checkout    = "$env:LOCALAPPDATA\hermes\hermes-agent",
    [string]$Branch      = "main",
    [int]   $WaitMinutes = 45,
    [int]   $SlowProbeSeconds = 60,
    [string]$Log         = "D:\hermes-test\finish-desktop-update.log"
)

$ErrorActionPreference = "Continue"
$hermes = Join-Path $HermesHome "bin\hermes.exe"

function Say([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

Say "start: checkout=$Checkout hermes=$hermes"

# 1. Wait for the app to exit (its Job Object would otherwise keep the rebuild blocked).
$deadline = (Get-Date).AddMinutes($WaitMinutes)
Say "waiting for Hermes.exe to exit (budget $WaitMinutes min)"
while ((Get-Date) -lt $deadline) {
    if (@(Get-Process -Name Hermes -ErrorAction SilentlyContinue).Count -eq 0) { break }
    Start-Sleep -Seconds 10
}
if (@(Get-Process -Name Hermes -ErrorAction SilentlyContinue).Count -gt 0) {
    Say "ABORT: Hermes.exe still running after the wait budget"
    exit 3
}
Say "app closed"

# 2. Probe the git route (bimodal: 1-2 s = go, tens of seconds = the updater's own 300 s cap will bite).
$probe = Measure-Command {
    git -C $Checkout ls-remote --heads origin $Branch 2>&1 | Out-Null
}
Say ("git probe: {0:N1}s" -f $probe.TotalSeconds)
if ($probe.TotalSeconds -gt $SlowProbeSeconds) {
    Say "ABORT: route is slow right now -- retry later"
    exit 4
}
# Pre-warm the pack so the updater's capped fetch has almost nothing to transfer.
$fetch = Measure-Command { git -C $Checkout fetch origin $Branch 2>&1 | Out-Null }
Say ("git fetch pre-warm: {0:N1}s" -f $fetch.TotalSeconds)

# 3. Update through the normal gateway mode path.
Say "running: hermes update --yes --gateway --force --branch $Branch --keep-stash"
& $hermes update --yes --gateway --force --branch $Branch --keep-stash 2>&1 | ForEach-Object { Say "update| $_" }
Say "update exit=$LASTEXITCODE"

# 4. Verify the packaged app is at HEAD; force-build when it is not.
$head  = (git -C $Checkout rev-parse HEAD).Trim()
$stamp = Join-Path $Checkout "apps\desktop\release\win-unpacked\resources\install-stamp.json"
function Get-StampCommit {
    if (-not (Test-Path $stamp)) { return "<no stamp>" }
    try { return (Get-Content $stamp -Raw | ConvertFrom-Json).commit } catch { return "<unreadable>" }
}
$built = Get-StampCommit
Say "HEAD=$head stamp=$built"
if ($built -ne $head) {
    Say "packaged app is stale -- building"
    & $hermes desktop --force-build --build-only 2>&1 | ForEach-Object { Say "build| $_" }
    $built = Get-StampCommit
    Say "after build: stamp=$built head=$head"
}

# 5. Relaunch the app and confirm the gateway is alive.
$exe = Join-Path $Checkout "apps\desktop\release\win-unpacked\Hermes.exe"
if (Test-Path $exe) {
    Start-Process $exe | Out-Null
    Say "desktop relaunched: $exe"
} else {
    Say "WARN: $exe is missing -- run 'hermes desktop --force-build --build-only' by hand"
}
& $hermes gateway status 2>&1 | ForEach-Object { Say "gateway| $_" }

if ($built -eq $head) { Say "done: app rebuilt to HEAD" ; exit 0 }
Say "done with a stale app (stamp != HEAD)"
exit 5
