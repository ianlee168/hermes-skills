' Hidden-task wrapper: run a command with NO visible window.
'
' Register the Windows Scheduled Task action as:
'     wscript.exe //B <path-to-this-file>.vbs
'
' Why: Task Scheduler gives a console program (powershell.exe / cmd.exe / python.exe) a REAL
' console window, so a recurring task flashes in front of the user on every tick. wscript.exe is
' a GUI host with no console at all, and Run(cmd, 0, False) starts the real command with window
' style 0 = hidden. //B makes wscript batch-mode so an unexpected VBS error cannot pop a dialog.
'
' Keep this file ASCII-only: cmd and PowerShell 5.1 decode non-ASCII without a BOM as ANSI and
' can fail to parse.
'
' After registering, verify the action really is wscript:
'     powershell -NoProfile -Command "(Get-ScheduledTask -TaskName '<Name>').Actions | Format-List Execute,Arguments"
' Then trigger it once and confirm the target's log gained a line and no window appeared.

Set sh = CreateObject("WScript.Shell")
' window style 0 = hidden, bWaitOnReturn = False
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\path\to\target.ps1""", 0, False
