# bsod_watch.ps1 关键片段（可直接复用）

## 真实崩溃时刻（6008 解析）

```powershell
$s6008 = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='EventLog'; Id=6008; StartTime=$ev.TimeCreated.AddHours(-12); EndTime=$ev.TimeCreated.AddMinutes(5)} |
         Sort-Object TimeCreated -Descending | Select-Object -First 1
if ($s6008) {
  $tm = [regex]::Match($s6008.Message, '(\d{1,2}:\d{2}:\d{2})')
  if ($tm.Success) {
    $t = [datetime]::ParseExact(($s6008.TimeCreated.ToString('yyyy-MM-dd') + ' ' + $tm.Groups[1].Value), 'yyyy-MM-dd HH:mm:ss', $null)
    if ($t -gt $ev.TimeCreated) { $t = $t.AddDays(-1) }
    $realCrash = $t
  }
}
```

## 故障存储段（责任模块）

```powershell
$wer = Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Windows Error Reporting'; Id=1001; StartTime=$realCrash.AddMinutes(-3); EndTime=$realCrash.AddMinutes(60)}
foreach ($w in $wer) {
  if ($w.Message -match 'BlueScreen') { $b = [regex]::Match($w.Message, '故障存储段\s*([^，,\r\n]+)') }
}
```

## 微信发送判成功

```powershell
$out = (& $HermesExe send -t weixin -s '[蓝屏监控]' -f $MsgFile --json 2>&1 | Out-String)
$ok  = ($LASTEXITCODE -eq 0) -and ($out -notmatch '"error"\s*:\s*"')
```

## 注册任务（提权后执行）

```powershell
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\<user>\bsod-watch\bsod_watch.ps1" -Mode collect'
$t = New-ScheduledTaskTrigger -AtStartup; $t.Delay = 'PT1M'
$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'Hermes-BSOD-Collect' -TaskPath '\Hermes\' -Action $a -Trigger $t -Principal $p -Settings $s -Force

# 通知任务：登录触发 + 每 30 分钟重复
$t2 = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"; $t2.Delay='PT45S'
$rep = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$t2.Repetition = $rep.Repetition
```
