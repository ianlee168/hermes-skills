# check-wol-boot.ps1 - one-shot Wake-on-LAN verification report (110me / 50.110).
# Triggered at next startup by the scheduled task "wol-verify-once".
# Writes a plain-text report, then deletes that task and this script's task entry.
# ASCII only on purpose: PowerShell 5.1 reads .ps1 as ANSI and non-ASCII breaks parsing.
# No window, no popup, no resident process.

$ErrorActionPreference = 'SilentlyContinue'
$dir = 'D:\hermes-test\wol-verify'
$out = Join-Path $dir 'wol-test-result.txt'

$L = New-Object System.Collections.Generic.List[string]
$L.Add('=== Wake-on-LAN boot verification (110me / 50.110) ===')
$L.Add('Report written : ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'))
$L.Add('')

$os = Get-CimInstance Win32_OperatingSystem
$L.Add('LastBootUpTime : ' + $os.LastBootUpTime)
$L.Add('Uptime at write: ' + ((Get-Date) - $os.LastBootUpTime))
$L.Add('')

$L.Add('--- powercfg /lastwake ---')
$L.Add((powercfg /lastwake | Out-String).Trim())
$L.Add('')

$L.Add('--- boot / shutdown events (newest 10) ---')
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ID=6005,6006,1074,109,41} -MaxEvents 10
if ($ev) { $L.Add(($ev | Select-Object TimeCreated, Id, ProviderName | Format-Table -AutoSize | Out-String).Trim()) }
else { $L.Add('(none readable)') }
$L.Add('')

$L.Add('--- Kernel-Power events (last 3h, wake-source text) ---')
$kp = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; StartTime=(Get-Date).AddHours(-3)} -MaxEvents 12
if ($kp) {
  foreach ($e in $kp) {
    $msg = ($e.Message -replace '\s+', ' ')
    if ($msg.Length -gt 220) { $msg = $msg.Substring(0, 220) }
    $L.Add(('[{0}] id={1}  {2}' -f $e.TimeCreated, $e.Id, $msg))
  }
} else { $L.Add('(none in window)') }
$L.Add('')

$L.Add('--- NIC (Realtek wired) state ---')
$nic = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'Realtek' }
if ($nic) {
  $L.Add(('Name={0} Status={1} LinkSpeed={2} Mac={3}' -f $nic.Name, $nic.Status, $nic.LinkSpeed, $nic.MacAddress))
  $pm = Get-NetAdapterPowerManagement -Name $nic.Name
  if ($pm) { $L.Add(('WakeOnMagicPacket={0} WakeOnPattern={1}' -f $pm.WakeOnMagicPacket, $pm.WakeOnPattern)) }
  $L.Add('Wake armed devices:')
  $L.Add((powercfg /devicequery wake_armed | Out-String).Trim())
} else { $L.Add('(Realtek adapter not found)') }
$L.Add('')
$L.Add('Interpretation: if LastBootUpTime matches the minute when 161jie sent the')
$L.Add('magic packet, BIOS-level Wake-on-LAN from S5 works and 110me can be woken')
$L.Add('for GPU work at any hour.')

# write report (fresh content every run)
$L -join "`r`n" | Set-Content -Path $out -Encoding UTF8

# self-cleanup: remove the one-shot trigger so nothing repeats.
# (registered either as a scheduled task or as a file in the Startup folder -
#  the latter is used when the session is not elevated)
schtasks /Delete /TN "wol-verify-once" /F | Out-Null
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$me = Join-Path $startup 'wol-verify-once.vbs'
if (Test-Path $me) { Remove-Item $me -Force }
