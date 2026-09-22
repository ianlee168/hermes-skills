' run-hidden.vbs - launch the WoL verification script with no console window.
' Same convention as Hermes_Gateway.vbs / laya-guard.vbs on 50.110:
' wscript //B  -> batch mode, no UI, no popups.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -NonInteractive -File ""D:\hermes-test\wol-verify\check-wol-boot.ps1""", 0, False
