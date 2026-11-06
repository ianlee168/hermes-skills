# shell-guard.ps1 — 登录后自检桌面外壳(explorer.exe 任务栏/桌面)
# 背景: ExplorerPatcher 的任务栏注入(ep_taskbar.ge.dll)在冷启动首次登录时会卡死外壳,
#       表现为「黑屏/空任务栏,进不去桌面」,以往只能手动重启 explorer 或重启整机。
# 本脚本在登录后延时自检,发现外壳没起来或已饿死,自动重启 explorer,恢复桌面。
param(
  [int]$DelaySeconds = 45,
  [int]$MonitorMinutes = 5,
  [int]$IntervalSeconds = 15,
  [int]$MaxAttempts = 3,
  [switch]$DryRun
)

$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Log  = Join-Path $Root 'shell-guard.log'

function Log([string]$m) {
  try { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Out-File -FilePath $Log -Append -Encoding utf8 } catch {}
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ShellGuard {
  [DllImport("user32.dll", CharSet = CharSet.Unicode)]
  public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
  [DllImport("user32.dll")]
  public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam,
      uint fuFlags, uint uTimeout, out IntPtr lpdwResult);
}
'@

$SMTO_ABORTIFHUNG = 0x0002
$WM_NULL = 0x0000

# 返回状态:Ok / NoTaskbar / Hung
function Get-ShellState {
  $tray = [ShellGuard]::FindWindow('Shell_TrayWnd', $null)
  if ($tray -eq [IntPtr]::Zero) { return 'NoTaskbar' }
  $res = [IntPtr]::Zero
  $r = [ShellGuard]::SendMessageTimeout($tray, $WM_NULL, [IntPtr]::Zero, [IntPtr]::Zero, $SMTO_ABORTIFHUNG, 5000, [ref]$res)
  if ($r -eq [IntPtr]::Zero) { return 'Hung' }
  return 'Ok'
}

function Restart-Shell {
  Log "restarting explorer.exe"
  Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 3
  Start-Process explorer.exe
  Start-Sleep -Seconds 12
}

Log "=== guard start (delay=${DelaySeconds}s monitor=${MonitorMinutes}min dryrun=$DryRun) ==="
Start-Sleep -Seconds $DelaySeconds

$deadline = (Get-Date).AddMinutes($MonitorMinutes)
$attempts = 0
$badStreak = 0

while ((Get-Date) -lt $deadline) {
  $state = Get-ShellState
  if ($state -eq 'Ok') {
    $badStreak = 0
    Log "shell OK"
  } else {
    $badStreak++
    Log "shell state=$state (streak=$badStreak)"
    if ($badStreak -ge 2 -and $attempts -lt $MaxAttempts) {
      if ($DryRun) { Log "DRYRUN: would restart explorer" }
      else { $attempts++; Restart-Shell }
      $badStreak = 0
    }
  }
  Start-Sleep -Seconds $IntervalSeconds
}

$final = Get-ShellState
Log "=== guard end: final=$final attempts=$attempts ==="
