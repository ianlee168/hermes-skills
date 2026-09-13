# HA doorbell / Windows native toast
# Usage: powershell -File toast.ps1 -DataFile <json>
# json: { "title": "...", "body": "...", "image": "C:\\path\\shot.jpg",
#         "aumid": "Hermes.Doorbell", "scenario": "alarm", "button": "忽略" }
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 as ANSI
# unless it has a UTF-8 BOM, so Chinese literals here would turn into garbage.
param([Parameter(Mandatory=$true)][string]$DataFile)

$ErrorActionPreference = 'Stop'
$raw  = [System.IO.File]::ReadAllText($DataFile, [System.Text.Encoding]::UTF8)
$data = $raw | ConvertFrom-Json

$aumid = if ($data.aumid) { $data.aumid } else { 'Hermes.Doorbell' }
$btn   = if ($data.button) { [string]$data.button } else { [string][char]0x5FFD + [char]0x7565 }  # 忽略

function Esc([string]$s) {
  if ($null -eq $s) { return '' }
  return $s.Replace('&','&amp;').Replace('<','&lt;').Replace('>','&gt;')
}

$title = Esc $data.title
$body  = Esc $data.body
$btnE  = Esc $btn
$img   = ''
if ($data.image -and (Test-Path -LiteralPath $data.image)) {
  $full = (Resolve-Path -LiteralPath $data.image).Path
  $img = '<image placement="hero" src="file:///' + ($full -replace '\\','/') + '"/>'
}

$xml = @"
<toast duration="long" scenario="$($data.scenario)">
  <visual>
    <binding template="ToastGeneric">
      <text>$title</text>
      <text>$body</text>
      $img
    </binding>
  </visual>
  <actions>
    <action content="$btnE" arguments="dismiss" activationType="system" />
  </actions>
</toast>
"@

# leave the built XML on disk for debugging / verification
$xmlOut = Join-Path (Split-Path -Parent $DataFile) 'last_toast.xml'
[System.IO.File]::WriteAllText($xmlOut, $xml, [System.Text.UTF8Encoding]::new($false))

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = New-Object Windows.UI.Notifications.ToastNotification $doc
$toast.Tag = 'doorbell'
$toast.Group = 'ha'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($aumid).Show($toast)
Write-Output "toast shown"
