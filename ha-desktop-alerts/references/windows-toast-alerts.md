# Windows 桌面投递层:双路提醒 + Toast 验证 + 全屏静音坑

用户对"门铃/事件 → 电脑"的既定要求是**两路都要**:

| 通道 | 定位 |
|---|---|
| 自己的置顶大弹窗(tkinter Toplevel) | **主力**。不受系统通知设置/免打扰影响,一定看得见 |
| Windows 原生 Toast(系统通知) | **兜底**。进通知中心,错过还能 Win+N 翻到;可带图 |

本文件只讲 Windows 侧怎么发/怎么验。事件源见 `ha-mihome-event-sources.md`,弹窗本体与开机自启见
skill `windows-strong-reminders`。

## 1. Toast 的最小可用写法(零依赖)

Windows 原生 Toast 用 WinRT API 直接发:**不需要 HASS.Agent**,也不需要 BurntToast / winrt 之类第三方包。

- **内容不要走命令行参数**(中文会被命令行编码搞坏)→ python 先写一个 UTF-8 的 JSON,ps1 用
  `[System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)` + `ConvertFrom-Json` 读。
- python 侧用 `subprocess.Popen(["powershell","-NoProfile","-ExecutionPolicy","Bypass",
  "-File", <toast.ps1>, "-DataFile", <json>], creationflags=0x08000000)`(CREATE_NO_WINDOW,不闪黑窗)。
- 现成脚本:`templates/toast.ps1`(可直接复制走)。要点:
  - `<toast duration="long" scenario="alarm">` —— `long` 停留更久;`alarm` 是最高优先级场景
    (**仍绕不过下面第 3 节的横幅抑制**)。
  - 图片:`<image placement="hero" src="file:///C:/path/shot.jpg"/>` —— 本地图要转成
    `file:///` + 正斜杠;没图就整行省略(先 `Test-Path` 判断)。
  - 按钮:`<action content="忽略" arguments="dismiss" activationType="system"/>`。
  - 文本要做 XML 转义(`& < >`),否则标题里的符号会让整条通知静默失败。
- **通知抬头(应用名)在 HKCU 注册即可,无需管理员**:
  ```
  reg add "HKCU\Software\Classes\AppUserModelId\<AUMID>" /v DisplayName /t REG_SZ /d "<显示名>" /f
  ```
  再用 `ToastNotificationManager::CreateToastNotifier("<AUMID>").Show($toast)` 发。
- ❌ 别用 `MessageBox` 或任何需要人点击的对话框做提醒(无人点击会挂死)。

## 2. 验证"到底发出去没有"(不靠肉眼)

- **投递凭证**:`[Windows.UI.Notifications.ToastNotificationManager]::History.GetHistory('<AUMID>')`
  → 条数 >0 即证明**已进通知中心**,与"屏幕上有没有横幅"是两件事。
- **抓整屏**:`computer_use` 抓屏只抓**当前前台窗口**,系统 Toast/其它覆盖层不在画面里 →
  看不到横幅不能证明没发。要抓多显示器整屏得自己来:
  ```powershell
  Add-Type -AssemblyName System.Drawing, System.Windows.Forms
  $b = [System.Windows.Forms.SystemInformation]::VirtualScreen      # 多显示器总区域
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  ([System.Drawing.Graphics]::FromImage($bmp)).CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
  $bmp.Save('<out.png>', [System.Drawing.Imaging.ImageFormat]::Png)
  ```
  (整屏可能几千像素宽,先裁右下角/缩图再看,别把巨图直接塞进上下文。)

## 3. ⚠️ 横幅被"全屏应用"静音(最容易误判的一条)

Windows 默认规则:**"全屏时"只显示闹钟类 / 不弹通知横幅**。而 **agent 自己驱动桌面的进程
(cua-driver.exe 等)会被判定成前台全屏应用** → 结果就是:通知条数在涨,横幅死活看不见,害人去查代码。

判据(一次看清):
```
HKCU\Software\Microsoft\Windows\CurrentVersion\Notifications\QuietHours
    FullScreenProcess     ← 当前被判定的全屏进程(看到 cua-driver.exe 就破案了)
    QuietHoursServiceState← 0 = 免打扰本身是关的
HKCU\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings
    NOC_GLOBAL_SETTING_TOASTS_ENABLED 不存在 = 通知总开关是开的(默认)
```

- 结论:**agent 在后台测 Toast 时,不要用"屏幕上看不到"当结论**;用 History 条数证明已投递,
  并在交付说明里主动给用户开关:设置 → 系统 → 通知 → 最下方"全屏时" → 选"显示通知"。
- 这也正是"大弹窗当主力"的理由:自己的置顶窗**不受**系统通知/免打扰设置影响。

## 4. 常驻 watcher 的重启姿势

- 按**命令行**匹配来杀旧实例,不靠 PID 文件:
  ```powershell
  $p = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
         Where-Object { $_.CommandLine -like '*<脚本名>*' })
  $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  ```
  ⚠️ `@()` 包住、并且**列表与动作分成两句**:把 `Write-Output` 的字符串和返回的对象混在一个
  函数里返回,`$_.ProcessId` 会是 null → `Stop-Process` 报"无法绑定参数 Id"。
- 杀完等 2~3 秒再起新实例(否则旧进程还在监听,会出现两条弹窗)。
- 起来后**回读日志**确认出现新的"已连接"时间戳,再回报用户;venv 里 1 个逻辑实例 = 2 个 python.exe
  (启动器 + 真身),别当重复实例。
