---
name: windows-port-squat-popup
description: Use when windows pop up repeatedly or a port looks dead.
version: 1.0.0
author: Hermes Agent (50.110)
license: MIT
metadata:
  hermes:
    tags: [Windows, Networking, Ollama, Diagnostics, Automation]
    related_skills: [web-page-fault-triage, windows-peripheral-diagnostics, hermes-cron-troubleshooting]
triggers:
  - "自动弹窗口"
  - "莫名弹窗"
  - "ollama 自己启动"
  - "端口不通但进程在"
  - "server not ready"
---

# Windows 弹窗 / 端口假死:portproxy 抢占 + 自动化误判

## When to Use

- 用户说「某个程序(尤其 Ollama / 托盘类 GUI)不停地自动弹窗口,我没启动它」。
- 本地 `http://127.0.0.1:<port>` 超时/连接挂死,但进程明明在跑、`netstat` 也显示 LISTENING。
- 某服务的 GUI 或客户端反复打日志 `server not ready / timeout waiting`。
- 局域网其它机器连本机某端口失败,而本机自己连又是好的(或相反)。

## 核心因果链(2026-11-20 实测)

```
遗留的 netsh portproxy 规则 (0.0.0.0:<port> -> 死地址)<-iphlpsvc 持有>
   ↓ 抢占 IPv4:<port>,把请求转发到不存在的目标
探活脚本硬编码 127.0.0.1  →  每次都超时  →  判定“服务死了”
   ↓
每 N 分钟启动一次 GUI 版程序拉活(window style 1)
   ↓
GUI 程序发现已有实例,先建窗口 + focus 现有实例再退出  →  用户看到“不停弹窗”
```

要点:**服务其实一切正常**(真的监听在 `[::]:<port>`,IPv6 栈),坏的是探活路径。所以别去重启/重装服务,先验连通性矩阵。

## 诊断步骤(按序,全部只读)

```bash
# 1. 谁在弹?真实进程与父子链
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name like '%<exe>%'\" | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | Format-List"

# 2. 弹窗时间是否等间隔?(等间隔 ≈ 计划任务/守护脚本,不是崩溃重启)
#    查 GUI 程序自己的日志:
#      %LOCALAPPDATA%\Ollama\app.log  (其它程序同名 app.log / *.log)
#    关键行: "sent focus request to existing instance" + "existing instance found, exiting"
#    = 这次启动只干了“弹个窗口然后退”,说明有外力在反复拉起它

# 3. 谁在反复拉起?
powershell -NoProfile -Command "Get-ScheduledTask | Where-Object { \$_.TaskName -match '<关键词>' } | Select TaskPath,TaskName,State | Format-Table -AutoSize"
powershell -NoProfile -Command "Get-ScheduledTaskInfo -TaskName '<任务名>' | Select LastRunTime,NextRunTime,LastTaskResult | Format-List"
Export-ScheduledTask -TaskName '<任务名>'   # 看 Action 指向哪个 vbs/ps1/bat,再读那个脚本

# 4. ★ 连通性矩阵 —— 这一步定位真凶
netstat -ano | grep ":<port>" | grep -i LISTEN      # 注意同一个端口出现两个不同 PID = 双绑定
netsh interface portproxy show all                 # 有 0.0.0.0:<port> 转发 = 抢占嫌疑
for u in "http://127.0.0.1:<port>/" "http://localhost:<port>/" "http://[::1]:<port>/" "http://<LAN_IP>:<port>/"; do
  printf '%-40s ' "$u"; curl -s -m 5 -g -o /dev/null -w 'code=%{http_code} t=%{time_total}\n' "$u"
done
#   典型指纹:127.0.0.1 超时(code=000,t≈超时值),而 localhost / [::1] 200 → portproxy 抢占 IPv4

# 5. 抢占者是谁(确认是 iphlpsvc 而不是别的程序)
powershell -NoProfile -Command "Get-CimInstance Win32_Service | Where-Object {\$_.ProcessId -eq <占用PID>} | Select Name,DisplayName"
```

## 修复

1. **脚本层(不需提权,先做,立刻止血)**
   - 探活改用 `localhost` / `[::1]`,**永不硬编码 127.0.0.1**;
   - 探活要有显式超时(WinHttp `SetTimeouts 1000,1000,3000,3000`),别用 MSXML 默认超时——能卡住整个任务;
   - 保活**只启动无窗口的 serve 子命令**(如 `ollama.exe serve`,window style 0),**绝不启动 GUI 主程序**;GUI 程序即使已有实例也会先弹窗口再 focus。
   - `wscript.exe //B` + `sh.Run cmd, 0, False` = 全程无窗口的既定姿势。
   - 改前先 `cp` 一份 `.bak-<时间戳>`;VBScript 大小写不敏感,**别让 Dim 的名字与 Const 重名**(会 “Name redefined” 编译失败,rc=1 且什么都不做,静默失效)。

2. **系统层(删 portproxy,必须提权 + 用户当轮同意)**
   ```bash
   # 先留回滚命令(把它原样贴给用户/写进记录)
   netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=<port>   # 计划
   netsh interface portproxy add    v4tov4 listenaddress=0.0.0.0 listenport=<port> connectaddress=<旧目标> connectport=<port>   # 回滚
   # 提权执行(UAC 会弹一次,让用户点)
   powershell -NoProfile -Command "Start-Process netsh -ArgumentList 'interface','portproxy','delete','v4tov4','listenaddress=0.0.0.0','listenport=<port>' -Verb RunAs -Wait -PassThru | Select ExitCode"
   ```
   未提权直接跑 netsh 会报「请求的操作需要提升(作为管理员运行)」——这是正常的,不要反复重试。

## 验证(缺一不可)

```bash
netsh interface portproxy show all      # 目标规则消失
netstat -ano | grep ":<port>" | grep -i LISTEN   # 只剩一个所有者
for u in 127.0.0.1 localhost [::1] <LAN_IP>; do curl 各一圈,全部 200; done
# 端到端:等下一个计划任务周期(通常 5 分钟)后确认 —— 不产生新日志行、不产生新进程 PID
# 跨机链路:从真正使用方那台机器 curl 本机:<port>(例:ssh <NAS> 'curl ... http://<LAN_IP>:<port>/')
```

## 坑

- **只看 `tasklist` 会漏掉抢占者**:portproxy 的监听 socket 属于 `svchost.exe`(iphlpsvc),不是目标程序。`netstat -ano` 同端口两个 PID 是唯一线索。
- **别把「探活失败」当成「服务挂了」**:先跑连通性矩阵。本次真凶是探活路径被劫持,重启服务一百次也没用。
- **`ping <portproxy目标>` 能通不代表目标活着**:目标若是 WSL / 虚拟网卡的地址,主机本地 ping 由协议栈自己回 0ms,而它的服务早就停了。判活一律用 curl 拿 HTTP 码。
- **GUI 托盘程序不能当保活工具**:0.40+ 的 `ollama app.exe` 是 Tauri GUI,任何启动都会建窗口并 focus 已有实例。保活只能拉后台子命令。
- **修脚本后必须等一个真实触发的周期验证**,手动执行通过不等于任务调度下通过(任务用 `wscript //B` 而不是 `cscript`)。
- **弹窗时间是否落在某个“维护窗口”**:本例只在 00:30–01:30 弹(那段是 NAS 借 GPU 跑 embedding 的时间窗)。窗口外不弹 → 直接指向带时间守卫的守护脚本,而不是崩溃循环。
- 顺带收益:这类 portproxy 残骸通常同时黑洞掉**局域网访问**(NAS/其它机连本机端口失败),删掉后要顺手从使用方机器验一次。
