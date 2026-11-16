# 写 PowerShell 排查脚本：省 15 分钟返工的自检清单

2026-11-16 实测：一次 Windows 启动项排查，约 15 分钟纯属返工（不是模型慢、不是中转池慢，
全是工具往返和踩坑重写）。下面每条都对应一次真实失败。

## 1. 永远写 .ps1 文件，用 `-File` 跑

```bash
# 对
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:/hermes-test/xxx.ps1"

# 错：bash 会先把 $_ $k $env: 展开掉
powershell.exe -NoProfile -Command "Get-Process | Where-Object { $_.Name -like 'MuMu*' }"
```

MSYS 把 `$_` 展开成 `/c/Users/<user>`，命令变成 `Where-Object { /c/Users/<user>.Name ... }`，
报错还会**每一行管道项刷一遍**（本次刷了 70KB 输出）。反斜杠、`{}`、`!` 同理。

## 2. ps1 内一个字的中文都不许有

注释、字符串、日志文案都算。Windows PowerShell 5.1 把**无 BOM 的 UTF-8 当 GBK 读**，
中文被切成半个字符，吞掉后面的引号或换行：

```
表达式或语句中包含意外的标记"}"
字符串缺少终止符
```

而且**报错行号会漂**（真实案例：第 6 行的中文注释，报错指向第 9 行和第 33 行）。
需要中文输出就在 PowerShell 里用 `[char]` 拼或干脆写英文。

## 3. 写完立刻语法自检（1 秒，别等提权往返）

```powershell
$f = 'D:\hermes-test\xxx.ps1'
$errs = $null
[void][System.Management.Automation.Language.Parser]::ParseInput((Get-Content -Raw $f), [ref]$null, [ref]$errs)
if ($errs) { $errs | ForEach-Object { "line " + $_.Extent.StartLineNumber + " :: " + $_.Message } } else { 'parse OK' }
```

写入前先跑这段，能省掉「提权 40 秒→脚本秒退→日志没生成→再查为什么」的整轮。

## 4. 结果落盘再读，别指望控制台

```powershell
$out -join "`r`n" | Out-File "$env:TEMP\diag.txt" -Encoding utf8
```

然后 `read_file`（或 `read_file` 那个绝对路径）。控制台是 GBK，中文一律变问号，
路径还会被截断成 `C:\Users\<user>.ProcessName` 这种误导性内容。

## 5. 提权：一次性打包，别分四轮

钩子（不需要弹 UAC，详见 `windows-vendor-software-cleanup` §1）：

```
C:\Users\<user>\bsod-watch\oneoff_elevated.cmd   ← 写 @echo off + powershell -File + del "%~f0"
trigger: Start-ScheduledTask -TaskPath '\Hermes\' -TaskName 'Hermes-BSOD-Notify'   （-TaskPath 必须带）
```

- 每轮往返 **40~240 秒**，分 4 轮就是 10 分钟 → 把所有需要管理员的事塞进**一个** ps1。
- 脚本开头 `New-Item -ItemType Directory -Force $logdir`，结尾写 `_done.txt`；
  另一个 cell 用 `_done.txt` 是否存在判断完成。不要靠轮询任务状态。
- 跑完确认 `oneoff_elevated.cmd` 已自删。

## 6. 不要在 execute_code 里长轮询

`execute_code` 的 cell 默认 300 秒上限，**一超时内核被杀、变量全丢**（本次丢了整轮提权结果，
还得重新确认卸载到底跑没跑）。正确姿势：

1. cell A：写脚本 + 触发任务，立刻返回；
2. cell B：只查 `_done.txt` / 日志文件；
3. 要等就在 cell 里 `time.sleep(30)` 一次，别写 30 次循环。

## 7. 禁止全盘递归搜索

```powershell
Get-ChildItem D:\,F:\,H:\ -Recurse -Filter x.exe   # 必超时，本次 283 秒白烧
```

限定到 `$env:APPDATA`、`C:\ProgramData`、`C:\Program Files` 这类**已知目录**；
实在要全盘就用 `dir /s /b` 并把结果写文件，分盘跑。

## 8. write_file 的坑

- 同一路径第二次写会被拒（"has not seen its full current content"）→ 改脚本就用新文件名（`xxx2.ps1`、`xxx3.ps1`），或先 `read_file` 再写。
- Windows 上 ps1 内容用 `write_file` 写（不要 echo/heredoc），避免 shell 二次转义。

## 9. 并行读

相互独立的读取（进程列表、注册表、事件日志、目录清单）在**同一个 cell 里一次发完**，
不要一个 cell 问一件事——每条往返都是时间。

## 一次典型的坏流程 vs 好流程

| 坏（本次实际） | 好 |
|---|---|
| 全盘递归找文件 → 283s 超时 | 只搜 AppData/ProgramData/Program Files |
| 中文注释 ps1 → 报错 → 改 3 遍 | 全 ASCII + 写入前 Parser 自检 |
| 提权分 4 轮，每轮等 40~240s | 一个 ps1 干完所有管理员活，`_done.txt` 收尾 |
| cell 里轮询 300s 被杀，状态丢失 | 触发即返回，下个 cell 查文件 |
| `-Command` 里塞 `$_` → 刷 70KB 报错 | 一律 `-File` 跑 ps1 |
