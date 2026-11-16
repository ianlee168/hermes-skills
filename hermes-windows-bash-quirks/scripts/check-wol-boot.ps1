# check-wol-boot.ps1 - one-shot report that proves whether a machine was woken
# remotely (Wake-on-LAN), and by what.
#
# Why it exists: after a cold (S5) boot, `powercfg /lastwake` always reports
# "wake history count 0", so the ONLY usable evidence is the boot timestamp
# aligned against the timestamp printed by whoever sent the magic packet.
# This script records that timestamp plus the surrounding evidence.
#
# Usage (run once at the next logon/startup, or by hand after a wake):
#   powershell -NoProfile -ExecutionPolicy Bypass -File check-wol-boot.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File check-wol-boot.ps1 -OutDir D:\hermes-test\wol-verify
#
# ASCII ONLY on purpose: PowerShell 5.1 reads .ps1 as ANSI, so non-ASCII
# (e.g. a Chinese adapter name) breaks parsing. Match adapters by their
# InterfaceDescription instead of typing a localized name.
#
# No window, no popup, nothing resident: it writes the report and then deletes
# the one-shot trigger that launched it (scheduled task and/or Startup entry).
param(
    [string]$OutDir = 'D:\hermes-test\wol-verify',
    [string]$TriggerName = 'wol-verify-once'
)

$ErrorActionPreference = 'SilentlyContinue'
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
$out = Join-Path $OutDir 'wol-test-result.txt'

$L = New-Object System.Collections.Generic.List[string]
$L.Add('=== Wake-on-LAN boot verification ===')
$L.Add('Report written : ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'))
$L.Add('')

$os = Get-CimInstance Win32_OperatingSystem
$L.Add('LastBootUpTime : ' + $os.LastBootUpTime)
$L.Add('Uptime at write: ' + ((Get-Date) - $os.LastBootUpTime))
$L.Add('')

$L.Add('--- powercfg /lastwake (expected: 0 on a cold boot) ---')
$L.Add((powercfg /lastwake | Out-String).Trim())
$L.Add('')

$L.Add('--- boot / shutdown events (newest 10) ---')
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ID=6005,6006,1074,109,41} -MaxEvents 10
if ($ev) { $L.Add(($ev | Select-Object TimeCreated, Id, ProviderName | Format-Table -AutoSize | Out-String).Trim()) }
else { $L.Add('(none readable)') }
$L.Add('')

$L.Add('--- Kernel-Power events, last 3h (wake-source text) ---')
$kp = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; StartTime=(Get-Date).AddHours(-3)} -MaxEvents 12
if ($kp) {
    foreach ($e in $kp) {
        $msg = ($e.Message -replace '\s+', ' ')
        if ($msg.Length -gt 220) { $msg = $msg.Substring(0, 220) }
        $L.Add(('[{0}] id={1}  {2}' -f $e.TimeCreated, $e.Id, $msg))
    }
} else { $L.Add('(none in window)') }
$L.Add('')

$L.Add('--- NIC state (match by description; localized names break .ps1 parsing) ---')
foreach ($nic in (Get-NetAdapter -Physical)) {
    $L.Add(('Name={0} Desc={1} Status={2} Link={3} Mac={4}' -f $nic.Name, $nic.InterfaceDescription, $nic.Status, $nic.LinkSpeed, $nic.MacAddress))
}
$L.Add('Wake armed devices (this is the authoritative list - Get-NetAdapterPowerManagement can throw error 31):')
$L.Add((powercfg /devicequery wake_armed | Out-String).Trim())
$L.Add('')
$L.Add('Interpretation: if LastBootUpTime matches the minute the remote side sent')
$L.Add('the magic packet, remote power-on works. If it does not, the firmware')
$L.Add('setting (BIOS/UEFI "Power On by PCIe") is the remaining suspect - that')
$L.Add('cannot be read from the OS, only tested.')

$L -join "`r`n" | Set-Content -Path $out -Encoding UTF8

# self-cleanup so nothing repeats
schtasks /Delete /TN $TriggerName /F | Out-Null
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$me = Join-Path $startup ($TriggerName + '.vbs')
if (Test-Path $me) { Remove-Item $me -Force }
