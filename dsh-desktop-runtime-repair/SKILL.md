---
name: dsh-desktop-runtime-repair
description: "Use when DeepSeek Harness 启动即崩、runtime 缺失。"
version: 1.0.0
author: 50.110 bot
license: MIT
platforms: [windows]
tags: [deepseek-harness, dsh-desktop, electron-updater, nsis, repair]
metadata:
  hermes:
    tags: [deepseek-harness, dsh-desktop, electron-updater, nsis, repair]
    triggers: ["DeepSeek Harness 打不开", "dsh-desktop 崩溃", "crash log host.log",
               "ENOENT office-skills", "skill-office 报错", "resources/runtime"]
---

# DeepSeek Harness 桌面端启动崩溃的修复（runtime 丢失）

## When to Use

- 用户发来 `crash-*-host.log`，DeepSeek Harness 双击无反应 / 启动即退。
- 日志里有 `ENOENT ... resources\runtime\office-skills\...` 或 `dsh-skill-office` 的 `readFileSync` 报错。
- 升级/自动更新后突然打不开，且 `resources\runtime` 是空目录。

## 症状

启动即退，`%APPDATA%\@deepseek-ai\dsh-desktop\logs\crash-*-host.log` 里出现：

```
DesktopHostFatalError: ENOENT: no such file or directory, open
  '<DSH_INSTALL_DIR>\resources\runtime\office-skills\office\SKILL.md'
    at ... dsh-skill-office/lib/index.js:64  (readFileSync)
```

首行栈常指向 `lib/main.js` + ChildProcess，会误导成"桌面壳崩"；真因在后面的 host diagnostic 里那条 `readFileSync`。

## 根因（先确认再动手）

`dsh-skill-office` 用 `assetRoot`（打包版由 desktop host 传 `resources\runtime\office-skills`）读 SKILL.md。
这个目录由 **NSIS 安装包 payload `$PLUGINSDIR/app-64.7z` 释放**，不在 app.asar 里。

判定是否"安装被截断"：

```bash
ls -la "/d/Programs/DeepSeek Harness/resources/runtime"   # 空 = 铁证
stat -c '%y %n' "/d/Programs/DeepSeek Harness/resources/runtime"
ls -la "$LOCALAPPDATA/@deepseek-aidsh-desktop-updater/pending"   # 有没有已下好的同版本安装包
```

真实案例（2026-11）：electron-updater 下好 293MB 安装包，10:24 开始装、10:25 建出 runtime 目录却 6144 个文件一个没写
⇒ 此后每次启动都崩，三条 crash log 堆在同一错误上。修复前**整盘对比**，别只补一个 SKILL.md：

```python
# <WORK_DIR>/dsh-fix/compare.py —— 用 write_file 落地，别用 heredoc 写含反斜杠的代码
import os
P, I = r'<WORK_DIR>/dsh-fix/payload', r'<DSH_INSTALL_DIR>'
SEP = chr(92)   # 别在 heredoc 里写双反斜杠，会被吞成单个，字符串直接语法错
# scan() 两边相对路径 + size，输出 missing / diff / extra
```

判读：`SIZE MISMATCH == 0` 且缺失全部落在 `resources/runtime/**` ⇒ 只需补 runtime；
`extra` 只有 `Uninstall DeepSeek Harness.exe` + `7zip-installer-*.txt` 属正常（NSIS 自己写的）。

## 修复（不重装、不跑安装器）

```bash
# 0. 先算 sha512 与 pending/update-info.json 比对，包不完整就重下
cd /d/hermes-test/dsh-fix
# 1. 从 updater 缓存里取出 payload
7z e "$LOCALAPPDATA/@deepseek-aidsh-desktop-updater/pending/deepseek-harness-*-win-x64.exe" \
  '$PLUGINSDIR/app-64.7z' -y
7z x app-64.7z -o./payload -y -bso0 -bsp0

# 2. 补 runtime（269MB / 6144 文件，7s 拷完）
python repair.py     # shutil.copytree(SRC, DST, dirs_exist_ok=True, copy_function=shutil.copy2)
```

拷完必须核对 **文件数与总字节数双向相等**（例：6144 files / 268,626,121 bytes），并抽查
`office-skills/office/SKILL.md`、`primary-runtime/dependencies/node/bin/node.exe`、`bin/node.cmd`、`cli/command-manager.js`。

## 验收

```bash
(nohup "/d/Programs/DeepSeek Harness/DeepSeek Harness.exe" >/dev/null 2>&1 &) ; sleep 45
tasklist /FI "IMAGENAME eq DeepSeek Harness.exe"          # 正常 5 个进程（main+renderer+host）
find "$APPDATA/@deepseek-ai/dsh-desktop/logs" -newermt "<刚启动的时间>" -type f | wc -l   # 必须 0
powershell -NoProfile -Command "(Get-Process 'DeepSeek Harness').MainWindowTitle"          # 有窗口标题
```

崩溃判据看的是 **新 crash log 为 0**，不是进程存活了几秒（以前是启动 ~1s 内必崩）。

## 坑

- **别急着跑安装器**：pending 里的 exe 就是同版本，重跑风险大于收益（同版本重装，且极可能又在 runtime 处截断）；从 payload 里补是最小改动。
- **app.asar 里也有 `dsh-skill-office/assets/office/SKILL.md`**，但打包版读的是 `resources/runtime/office-skills`；别拿 asar 里那份去凑（缺 node.exe/pnpm/primary-runtime，下一层还会崩）。
- **`7z l` 列表里 `resources\runtime` 只显示目录项**（Size=0 / Attributes=D），别据此断定 payload 里没文件；直接 `7z x` 出来数。
- **本机 bash heredoc 会吞反斜杠**：含反斜杠的 python 一律 `write_file` 落地再 `python x.py`。
- 用户数据在 `%APPDATA%\@deepseek-ai\dsh-desktop` 与 `~/.dsh`（profiles/sessions/credentials），补 runtime 不碰这些。
- 解包过程占 `<WORK_DIR>/dsh-fix` 约 1.4G（app-64.7z 292M + payload 约 1.1G），验收完按删除红线先问再清。
