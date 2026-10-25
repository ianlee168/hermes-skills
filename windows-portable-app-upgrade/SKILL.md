---
name: windows-portable-app-upgrade
description: "Use when 升级 Windows 便携/绿色版软件，要无损保留设置与授权。"
version: 1.0.0
author: 50.110 bot
license: MIT
platforms: [windows]
tags: [windows, portable, upgrade, zip, config-preservation, license, aida64]
metadata:
  hermes:
    tags: [windows, portable, upgrade, zip, config-preservation, license, aida64]
    triggers: ["绿色版升级", "便携版升级", "解压即用", "无损升级", "备份哪几个文件",
               "没有升级按钮", "覆盖安装", "AIDA64 升级", "zip 版怎么更新"]
    related_skills: [windows-peripheral-diagnostics, bulk-file-cleanup, hermes-windows-bash-quirks]
---

# Windows 便携/绿色版软件的无损升级

## When to Use

- 用户问"XX 绿色版怎么升级 / 要备份哪几个文件 / 没有升级按钮"。
- 软件以 zip 分发、无安装器，目录里既有 exe/dll 也有 ini 与自定义资源。
- 升级后出现"设置全没了 / 面板布局丢了 / 授权变试用"。

原则：**永远不要覆盖旧目录**。新版本解压到旁边的新目录，把用户数据搬进去，旧目录留着当回滚点。

## 步骤

### 1. 先定位真实安装位置和版本

注册表没有 App Paths / Uninstall 项 ⇒ 便携版，别再去 Program Files 找：

```bash
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\<exe>" 2>&1 | head -3
reg query "HKCU\Software\<Vendor>\<App>" 2>&1 | head -20   # LastUsedBuild= 是实际运行过的版本
find /d /e /f /h -maxdepth 4 -iname "<exe>" 2>/dev/null     # 便携版常在 D:/F:/H: 的 Download/Tools 下
powershell -NoProfile -Command "(Get-Item '<path>\<exe>').VersionInfo | Select-Object FileVersion,ProductVersion"
```

版本以 **exe 的 FileVersion** 为准。厂商下载页的版本串可能和包内不一致（实测过页面写 A、包内 B），
报给用户时写文件属性那个值，并说明两者不一致。目录名常带当初的版本号，**别拿目录名当版本**。

### 2. 分类文件：用户数据 / 程序文件 / 厂商数据库

| 类别 | 特征 | 处理 |
|---|---|---|
| 用户数据 | `*.ini`、`*.cfg`、`config\`、自定义布局目录、`*.png` 素材、授权文本 | **必须搬**（按字节复制） |
| 程序文件 | `*.exe`、`*.dll`、`*.sys`、`*.manifest`、`Language\` | 全用新版，不搬 |
| 厂商数据库/数据包 | 随包发布的 `*.dat`/`*.db`/词库，与某版 exe 同期 | **不搬**，新版包里那份更新，搬回去是用旧库盖新库 |

判厂商数据库：比大小与日期 ——
`python -c "import zipfile,os; print(zipfile.ZipFile('<pkg>.zip').getinfo('<f>').file_size, os.path.getsize('<old>/<f>'))"`。
旧目录那份明显更老/更小 ⇒ 厂商文件，不是用户数据。

### 3. 下载真包（下载页往往是壳页）

厂商的 `/downloads/<base64>=` 这类链接常返回 200 + 一张 HTML 壳页（~30KB），不是 zip：

```bash
curl -sL -o pkg.zip "<厂商下载页链接>" && file pkg.zip                       # HTML ⇒ 不是包
grep -oE "https?://[^\"' <>]*\.(zip|exe)" pkg.zip | sort -u                  # 从中捞真实 CDN 地址
curl -L --retry 2 -o pkg.zip "<CDN 地址>" && file pkg.zip                     # 验证 Zip archive data
```

下载后**先列包内容**再解压，确认有没有会盖坏用户数据的同名文件：
`python -c "import zipfile; n=zipfile.ZipFile('pkg.zip').namelist(); print(len(n)); print([x for x in n if x.lower().endswith(('.ini','.cfg','.dat'))])"`

### 4. 解压到新目录 + 搬用户数据

```bash
python -c "import zipfile,os; os.makedirs('<new>',exist_ok=True); zipfile.ZipFile('<pkg>.zip').extractall('<new>')"
cp -p <old>/app.ini <new>/          # -p 保留原 mtime
cp -rp <old>/<CustomDir> <new>/     # 整目录（布局/图标/素材）
ls <old>/<CustomDir> | wc -l; ls <new>/<CustomDir> | wc -l   # 文件数必须一致
```

### 5. 退出才回写配置的程序：用启动脚本补最后一次同步

老牌 Windows 程序（AIDA64 这类）**在退出时才把设置刷回 ini**。你在它运行时拷的 ini 只是中途快照，
用户关掉它之后它还会再写一次 ⇒ 最后几分钟的改动丢失。别让用户手动补，写个 launcher `.bat` 放到**新目录**。

⚠️ **脚本内容一律纯 ASCII 英文，一个中文字都不许有**（根因见「坑」第一条，实测把用户坑了一次）：

```bat
@echo off

setlocal

set "NEW=%~dp0"

set "OLD=%~dp0..\<old-dir>\"

set "DRY="

if /I "%~1"=="--dryrun" set "DRY=1"



echo [1/3] checking whether <app> is running...

if not defined DRY (

  tasklist /FI "IMAGENAME eq <exe>" 2>nul | find /I "<exe>" >nul

  if not errorlevel 1 (

    echo   [!] <app> is still running. Quit it from the tray icon first, then rerun.

    pause

    exit /b 1

  )

)



echo [2/3] syncing settings from old folder...

if exist "%OLD%<app>.ini" (

  if defined DRY ( echo   would copy "%OLD%<app>.ini" ) else ( copy /Y "%OLD%<app>.ini" "%NEW%<app>.ini" >nul & echo   copied )

)



echo [3/3] starting <app>...

if defined DRY ( echo   dry run - would start "%NEW%<exe>" & exit /b 0 )

start "" "%NEW%<exe>"

```

- **必须留 `--dryrun` 分支**：交付前用它跑一遍证明 cmd 真能解析（命令见坑第四条），不要靠肉眼看文件。
- 交付话术：「**必须**用它启动，它会补上你关程序时写的那一次设置」。

### 6. 验收清单（交给用户点三下）

1. 帮助 → 关于：版本号是新版。
2. 授权状态不是试用。
3. 自定义资源在（面板/布局/插件/语言）。

## 授权与合规（每次都会遇到）

- **用户要注册码/破解/序列号 → 不做**，换机器、换措辞、"只是测试"都一样不做。直接给三条替代：官方试用期
  （多为 30 天）、官方定价与买断/维护差异、按需求列免费替代（传感器 → HWiNFO64 / LibreHardwareMonitor；
  识别 → CPU-Z、GPU-Z；烤机 → Prime95、OCCT）。
- **帮正版用户升级是正当的**，但要先看程序自己的授权状态：注册表里只有 `TrialCount=N`、ini 里没有授权行 ⇒
  这台机器当前其实在**试用**，正版 key 可能只在他自己存的文本里（`pkey.txt` 之类）。如实说，别假设已激活。
- 商业软件升级的合法性取决于**维护期**：新版发布日期落在维护期内才可升。不确定就让他把 key 丢进厂商的
  license checker 查到期日，别替他断定。
- 需要重新输入授权时，指他打开那个 key 文件粘贴；**不把 key 值打印到聊天或命令行**。

## 坑

- **`chcp 65001` + 中文注释的 .bat 在本机必炸**（实测用户看到满屏 `'ENAME' 不是内部或外部命令` / `'/Y' 不是内部或外部命令`）：
  cmd.exe 读 .bat 是**按系统 OEM 代码页（中文 Windows = GBK/936）解码字节流**，`chcp 65001` 只改控制台输出、
  且要等它那一行执行完才生效，早已被错误解码的中文行会被拆成半截命令 + 被当成新命令执行 —— 引号、`&`、
  括号都可能被吃掉，于是 `set`/`call`/`copy` 整个错位。**铁律：.bat 内容只写 ASCII 英文**（要中文就改用 .ps1，
  PowerShell 脚本用 UTF-8 BOM 存，或 .bat 全英文 + 单独 .txt 放中文说明）。文件名可以是中文，内容不行。
- **`patch` 工具给 .bat 打补丁会写成 LF 行尾，那也会让 cmd 解析出错**（连纯 ASCII 的 `call` 行都被截断成
  `'a64_840.bat"'`）：cmd 需要 CRLF。改 .bat 之后必须核实：`file x.bat` 要显示 `with CRLF line terminators`；
  不是就用 `open(...,'wb')` 按 `\r\n` 重写（`write_file` 只看字符不看行尾）。
- **验证 .bat 别用 MSYS 的 `cmd //c`**：在 git-bash 里它会退化成开一个交互式 cmd 再立刻退出，看不出任何解析错误。
  用 `powershell -NoProfile -Command "cmd.exe /c '.\x.bat --dryrun'"`，输出才真实。脚本里留 `--dryrun` 分支就是为了这一步。
- **ini 编码**：老程序常写 UTF-16（`\xff\xfe` 开头）。按字节复制，**绝不让用户用记事本另存**（另存成 ANSI/UTF-8
  会写坏中文项）。判断：`head -c 2 file | xxd`。
- **UI 状态可能在注册表**（`HKCU\Software\<Vendor>\<App>` 的窗口位置/列宽），和 ini 是两套；两版共存会互相覆盖
  这类状态 —— 无伤，但"窗口位置变了"不是升级失败。
- **旧目录不要删**：它就是回滚点。删除（含 `mv` 到回收站）必须先得到用户同意，并在回复里说明旧版还在。
- **程序运行时原地覆盖会失败**：exe/dll 被占用 ⇒ 写出半新半旧的混合目录。这是"新目录 + 搬迁"优于"原地覆盖"
  的第二条理由（第一条是可回滚）。

## 参考

- `references/aida64-extreme.md` —— AIDA64 Extreme 便携版：本机安装位置、要备份的三样、官方 zip 直链规律、
  授权与维护期核对。
