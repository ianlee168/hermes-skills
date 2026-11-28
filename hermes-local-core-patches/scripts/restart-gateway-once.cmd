@echo off
rem One-shot detached gateway restart (used after applying local core patches).
rem Runs under Task Scheduler so it is NOT a child of the agent/gateway process tree.
timeout /t 5 /nobreak >nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*hermes_cli.main gateway run*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 6 /nobreak >nul
schtasks /Run /TN Hermes_Gateway
