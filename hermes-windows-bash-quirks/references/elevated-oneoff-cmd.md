# 用计划任务提权跑一次性脚本（one-off cmd）

50.110 上已验证的提权通道：计划任务 `\Hermes\Hermes-BSOD-Notify` → `wscript //B run_hidden.vbs` →
`C:\Users\<user>\bsod-watch\oneoff_elevated.cmd` → 真正要跑的 .ps1。需要管理员权限的活
（读 USB hub、装/卸驱动、抓提权程序窗口、改服务）都走这条路。

## 三个会让人白跑好几轮的点

1. **`oneoff_elevated.cmd` 末尾的 `del "%~f0"` 会让它每次跑完自删。** 下一次 `Start-ScheduledTask`
   依然“成功”，但 wrapper 找不到文件、什么都不干。**每轮改完脚本必须重新写一次这个 cmd**，
   否则会误判成“脚本坏了”。
2. **只看 `LastTaskResult=0` 不够**：那是上一次的残留值。判“真跑过”要同时看 `LastRunTime` 是刚才、
   以及输出文件的 mtime。`LastTaskResult=267009`（0x41301）= **任务仍在运行**，此时再 Start 不会起新实例，
   先 `Stop-ScheduledTask`。
3. **卡住的实例常常是上一次的提权进程没退**：`Get-CimInstance Win32_Process` 里 `Path`/`CommandLine`
   为空就是提权进程，普通权限 `taskkill /F` 会报“拒绝访问”，需另设一个更短的一次性任务去杀，或直接重起会话。
4. **`.cmd` 必须 CRLF 换行**：从 bash 用 heredoc（`cat > x.cmd <<'EOF'`）写出来是 LF-only，
   cmd.exe 会跑到中途**静默放弃** —— 文件自删了、`LastTaskResult=0`、`LastRunTime` 也是刚才，
   但里面每条命令都没执行（表现为“等半天没反应，又没任何报错”）。用 `printf '...\r\n' > x.cmd`
   或 python 以 `newline='\r\n'` 写。**判定换行是否生效的最快办法**：helper 第一行写
   `whoami /priv > D:\...\marker.txt`，marker 没出现就是换行问题，不要再去怀疑权限或任务配置。

## 让失败可见

```bat
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\path\to\task.ps1" > "D:\path\to\run.log" 2>&1
del "%~f0"
```

- 日志 **0 字节** = 连第一行都没执行到（Add-Type 编译、参数解析阶段就挂了），不是业务逻辑错。
- 日志里只有最后一句 `ok`、目标输出文件不存在 = 脚本真的跑完了但写错了路径/变量（例如改了 `$out` 却忘了同步）。
- 提权上下文里 `SetForegroundWindow` 抢不到前台，`CopyFromScreen` 会截到压在上面的另一个窗口；
  抓窗口一律用 `PrintWindow(hWnd, hdc, 2)`（见本 skill 的 `references/screen-ocr.md`）。
- 含中文的 `.ps1` 必须存成 **UTF-8 BOM**，否则 PowerShell 5.1 按 ANSI 解码，`endsWith('.lnk')`
  之类的校验会失败、路径变成乱码。

## 能力边界：管理员权限不等于能读一切

某些内核态结构体的偏移量（例如 `USB_NODE_CONNECTION_INFORMATION_EX` 的 Speed/ConnectionStatus）
并非“提权就能读对”。若要下“某口协商在 20 Gbps”这种结论，优先用能看到结果的现成工具
（UsbTreeView 等）或厂商手册规格，**不要用自己猜的结构体偏移量当结论**。
