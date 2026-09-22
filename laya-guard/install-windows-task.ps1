# Register the laya-guard resident service as a Windows Scheduled Task.
# English-only on purpose: PowerShell 5.1 reads .ps1 as ANSI, so non-ASCII
# comments break parsing.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-windows-task.ps1 `
#       -VbsPath "D:\tools\laya-guard.vbs"
#
# Mirrors the settings used by the resident Hermes gateway task on this class
# of machine: logon trigger, Limited run level, Interactive logon type,
# restart on failure 999x / 1 min.

param(
    [Parameter(Mandatory = $true)][string]$VbsPath,
    [string]$TaskName = "laya-guard",
    [string]$UserId   = "$env:USERDOMAIN\$env:USERNAME"
)

if (-not (Test-Path $VbsPath)) { throw "VBS not found: $VbsPath" }

$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('//B //Nologo "{0}"' -f $VbsPath)

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# ExecutionTimeLimit Zero = never kill the task. The default is 3 DAYS, which
# silently terminates a resident service - always set this explicitly.
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

$principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description 'laya-guard: local decision-model pre-gate for the Hermes agent (127.0.0.1:8799)' | Out-Null

Write-Output ("registered task '{0}' -> {1}" -f $TaskName, $VbsPath)

# Start it now and wait for the model to load (cold start ~10 s on CPU, ~5-8 s on GPU).
Start-ScheduledTask -TaskName $TaskName
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 5
    try {
        $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8799/health' -TimeoutSec 4
        if ($h.ready) {
            Write-Output ("ready=true | jev key loaded={0} | rss_mb={1}" -f $h.jev.configured, $h.rss_mb)
            $ready = $true
            break
        }
    } catch { }
}
if (-not $ready) { Write-Output 'service not ready after 90s - check the log under $HERMES_HOME/logs/' }

# Notes:
#   * jev.configured=false means the key file was not readable. Check
#     $HERMES_HOME/secrets/typesafe-jev.key exists (108 bytes, no trailing
#     newline) and that HERMES_HOME in the .vbs is a native Windows path.
#   * rss_mb is -1 on Windows (the service reads /proc/self/status) - expected.
#   * After changing thresholds, restart: Restart-ScheduledTask -TaskName <name>
