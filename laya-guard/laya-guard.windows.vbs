' ============================================================
'  laya-guard launcher for Windows (windowless, via Scheduled Task)
'
'  Usage: fill in the three paths below, then register a logon-trigger
'  Scheduled Task running:
'      wscript.exe //B //Nologo "<this file>"
'  (install-windows-task.ps1 does that for you.)
'
'  Why a .vbs: wscript + window style 0 starts the service with NO console
'  window, which is how the resident Hermes gateway on the same machine is
'  started. A plain .cmd/.bat would flash a console at every logon.
'
'  IMPORTANT: the paths below must be NATIVE Windows form (C:\ or D:\ ...).
'  An MSYS/Git-Bash style value like /c/Users/... handed to a native exe is
'  an invalid path on Windows: the service then silently fails to read its
'  Jev key file and writes its log into a junk C:\c\... tree.
' ============================================================
Option Explicit
Dim sh, env
Set sh = CreateObject("WScript.Shell")
Set env = sh.Environment("PROCESS")
env.Item("HERMES_HOME") = "<HERMES_HOME>"          ' e.g. C:\Users\<user>\AppData\Local\hermes
env.Item("HF_HOME") = "<HF_CACHE_DIR>"             ' e.g. D:\models\hf  (keeps weights off C:)
env.Item("PYTHONIOENCODING") = "utf-8"
' Kill switch: uncomment to make the service exit immediately (the plugin
' then fails open, i.e. it stops screening).
' env.Item("LAYA_GUARD_DISABLE") = "1"
sh.CurrentDirectory = "<PLUGIN_DIR>"               ' ...\hermes\plugins\laya-guard
sh.Run """<VENV_PYTHON>"" server.py", 0, False      ' e.g. D:\venvs\laya\Scripts\python.exe
