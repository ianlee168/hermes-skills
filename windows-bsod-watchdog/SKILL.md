---
name: windows-bsod-watchdog
description: "Use when Windows 蓝屏/自动重启要查原因或要加崩溃监控。取证+转储备份+微信告警。"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [windows, bsod, crash, dump, eventlog, scheduled-task, monitoring]
    related_skills: [hermes-cron-troubleshooting, windows-strong-reminders, ha-desktop-alerts]
---

# Windows 蓝屏取证与监控

## 1. 先取证（不猜，按顺序读日志）

| 来源 | 含义 |
|---|---|
| System log, `Microsoft-Windows-WER-SystemErrorReporting` ID **1001** | 蓝屏代码 + 4 个参数 + minidump 路径（事件时间=**重启之后**，不是崩溃时刻） |
| System log, `EventLog` ID **6008** | 真实崩溃时刻：`上一次系统的 HH:mm:ss ... 的关闭是意外的` → 用 `(\d{1,2}:\d{2}:\d{2})` 抓，事件日期与它拼 |
| System log, `Kernel-Power` ID **41** | 非正常关机；`Properties[0]`=bugcheck code、`[1..3]`=参数；PowerButtonTimestamp=0 表示不是按电源键 |
| Application log, `Windows Error Reporting` ID 1001, 事件名 BlueScreen | **故障存储段 = 责任模块**，形如 `AV_CCInputProtect_x64!DetachUsbKbDevice`（注意中文是「故障存储**段**」，且**没有冒号**：正则用 `故障存储段\s*([^，,\r\n]+)`） |
| 同上但事件名 LiveKernelEvent | 非致命（显卡黑屏 WATCHDOG、USBXHCI 命令中止等），与蓝屏不同源，别混为一谈 |
| `Microsoft-Windows-WHEA-Logger` | 硬件错误；有它才怀疑内存/CPU |
| 崩溃前 1 小时的 System 7045 | 期间加载的内核驱动（超频/监控/安全控件常在此列） |

minidump 文件名 `MMDDYY-NNNNN-NN.dmp` 里的数字**不是时间**。

## 2. 三个必踩的坑

- **C:\Windows\Minidump 对非管理员不可读**：`cmd dir` 会**误导性**地打印「找不到文件」，`icacls` 说拒绝访问，.NET `Directory.GetFiles` 抛 UnauthorizedAccessException。
  → 没提权就别下「转储已被清理」的结论（曾据此误报，实际 dump 好好躺在原处）。
- **SYSTEM 身份的计划任务对普通用户不可见**：`schtasks /query` 报拒绝访问、`Get-ScheduledTask` 直接不列它 → 验证任务是否真存在必须**提权再看**。
- **PS 5.1 读中文 .ps1 需要 UTF-8 BOM**：无 BOM 时按 ANSI 解码，中文全变乱码 → 正则静默失配（曾导致故障存储段永远抓不到）。
  写文件后统一转换：`[IO.File]::WriteAllText($p,[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8),(New-Object Text.UTF8Encoding($true)))`
  同类坑：`.cmd` 里的中文 `rem` 注释会被 GBK 解码成命令去执行 → .cmd 一律只写 ASCII。

## 3. 部署监控（已验证架构）

脚本 `%USERPROFILE%\bsod-watch\bsod_watch.ps1`，两个模式：

- `-Mode collect`（计划任务：**开机 + 60 秒，以 SYSTEM 运行，RunLevel Highest**）→ 只备份转储 + 写报告，不推送；用于抢在清理工具/系统清理之前把 .dmp 拷走（清理可能发生在登录前）。
- `-Mode all`（计划任务：**登录 + 45 秒，当前用户 RunLevel Highest，重复间隔 30 分钟 / 时长 P3650D**）→ 检测 + 报告 + 推送队列。
- 两个任务都放同一个路径（如 `\Hermes\`），注册用 `Register-ScheduledTask -Force`。
- 提权注册：写 `install.cmd` 调 `powershell -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList ...-File register.ps1"`，让用户在桌面点一次 UAC（一次注册、长期有效）。
- 桌面弹窗兜底：WinRT `ToastNotificationManager` + `CreateToastNotifier('Microsoft.WindowsPowerShell')`，本地即时可见。

## 4. 推送：必须带退避队列（iLink 限流）

- 一律 `hermes send -t weixin --json`：非 json 模式失败时退出码 1 但 stdout/stderr **全空**，错误只在 json 的 `error` 字段。成功判据 = exit 0 **且** 不匹配 `"error"\s*:\s*"`。
- iLink 每次尝试都会重置 30s 冷却 → **固定间隔重试永远失败**（实测三次连发全部 rate limited）。
  → 把待发消息**持久化到 state.json 的 pending 队列**（含 attempts / next / text），按 60/180/420/900/1800/3600 秒指数退避，**只有发送成功才出队**；30 分钟一次的任务 tick 天然当重试载体，最多 8 次后放弃但报告文件仍在本地。
- 通道长期风控（可达小时级）时主动推送会一直失败 → 让用户先给 bot 发一条消息刷新 context token；本地 Toast + 报告文件是保底通道。
- 更多 iLink/cron 投递坑见 skill `hermes-cron-troubleshooting`。

## 5. 转储备份的两条纪律

- 跳过 **> 1 GB** 的 dump（LiveKernelReports 根目录常驻几个 GB 的黑屏 dump）与**超过 30 天**的 LiveKernelReports；只记一行「已跳过」。
- LiveKernelReports 根目录与子目录**常有同名文件**（`WATCHDOG-YYYYMMDD-HHMM.dmp`）→ 目标名要带父目录前缀，否则互相覆盖（曾把 3.4 GB 的文件名盖在 3.5 MB 文件上）。
- **不自动删除旧备份**（删文件需用户逐次同意）；只在报告里给路径和体积，让用户决定。

## 6. 输出与答复口径

- 报告落 `reports\BSOD_<yyyyMMdd-HHmmss>.md`：代码+参数+责任模块+崩溃时刻+停机时长+期间加载的驱动+LiveKernelEvent+WHEA+转储路径+三条排查建议。
- 回答用户时明确区分：**是蓝屏/自动重启，还是更新或断电**（6008/41/1001 有其一即为崩溃；有没有 1074/6006 决定是否「干净关机」）。
- 「责任模块」里的模块名只是**栈上模块**，不是定罪书；结合该驱动的版本/签名日期/厂商与当天新装的软件（如网银安全控件、超频工具）再下结论，别把 0xA 一律归给硬件。
