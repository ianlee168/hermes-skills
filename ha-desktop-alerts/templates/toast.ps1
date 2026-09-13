# 事件 → Windows 原生通知(Toast)。由 python 调: powershell -File toast.ps1 -DataFile <json>
# json: {"title":"...","body":"...","image":"C:\\path\\shot.jpg","aumid":"Hermes.Doorbell","scenario":"alarm"}
# 前置(一次性,免管理员):
#   reg add "HKCU\Software\Classes\AppUserModelId\Hermes.Doorbell" /v DisplayName /t REG_SZ /d "门口门铃" /f
param([Parameter(Mandatory=$true)][string]$DataFile)

$ErrorActionPreference = 'Stop'
# 中文内容走 UTF-8 JSON 文件,不走命令行参数(命令行编码会搞坏中文)
$raw  = [System.IO.File]::ReadAllText($DataFile, [System.Text.Encoding]::UTF8)
$data = $raw | ConvertFrom-Json

$aumid = if ($data.aumid) { $data.aumid } else { 'Hermes.Doorbell' }
$scenario = if ($data.scenario) { $data.scenario } else { 'alarm' }

function Esc([string]$s) {
  if ($null -eq $s) { return '' }
  return $s.Replace('&','&amp;').Replace('<','&lt;').Replace('>','&gt;')
}

$title = Esc $data.title
$body  = Esc $data.body

$img = ''
if ($data.image -and (Test-Path -LiteralPath $data.image)) {
  $full = (Resolve-Path -LiteralPath $data.image).Path
  $img = '<image placement="hero" src="file:///' + ($full -replace '\\','/') + '"/>'
}

$xml = @"
<toast duration="long" scenario="$scenario">
  <visual>
    <binding template="ToastGeneric">
      <text>$title</text>
      <text>$body</text>
      $img
    </binding>
  </visual>
  <actions>
    <action content="忽略" arguments="dismiss" activationType="system" />
  </actions>
</toast>
"@

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = New-Object Windows.UI.Notifications.ToastNotification $doc
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($aumid).Show($toast)
Write-Output "toast shown"
