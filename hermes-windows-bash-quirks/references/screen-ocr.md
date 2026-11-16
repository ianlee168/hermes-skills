# 无视觉模型时，把屏幕上的数字读成文本（WinRT OCR）

用途：用户发来 AIDA64 / 传感器 / BIOS 截图，要读里面的数值；或者需要自己截某个程序窗口再读。
在 50.110 上实测可稳定读出 AIDA64 内存跑分表、ZenTimings 时序表（英文标签 + 数字）。

## 1. 拿到图片

- 用户发的图：路径形如 `D:\hermes-cache\cache\documents\native-inputs\<hash>\dashboard_*.png`。
- 自己截：**用 `PrintWindow(hWnd, hdc, 2)`，不要 `CopyFromScreen`。**
  从计划任务/后台进程里 `SetForegroundWindow` 抢不到前台，`CopyFromScreen` 截到的是
  压在上面的另一个窗口（实测截到 HWiNFO 而不是 ZenTimings，白跑一轮）。
  `PrintWindow` 的 flag=2（PW_RENDERFULLCONTENT）对 WPF/.NET 窗口也能出图，且不受遮挡影响。
  现成脚本：`D:\hermes-test\zentimings3.ps1`（PrintWindow 版）、`hwinfo-launch2.ps1`（等窗口出现再截）。

窗口句柄的取法：`Get-Process <name> | Where-Object { $_.MainWindowHandle -ne 0 }`。
**刚启动的程序常常还没建窗口**（标题是「正在分析…」、`MainWindowHandle=0`、rect 0x0）——
要循环重试（每 2s，最多 20–30 次），或先 `Start-Sleep 10+` 再取，别一次拿不到就判“程序坏了”。

**目标程序是提权进程时，普通权限 shell 连它的窗口都枚举不到**：`Get-Process` 拿到的
`MainWindowHandle` 恒为 `0`、`MainWindowTitle` 为空（HWiNFO 实测），`EnumWindows` 里按 pid 过滤也是空集。
这时 PrintWindow 这条路根本走不通，退一步：**抓整个桌面再裁区域看** ——
`[System.Windows.Forms.SystemInformation]::VirtualScreen` + `Graphics.CopyFromScreen` 存全屏 PNG，
再用 `vision_analyze(..., region=[x1,y1,x2,y2])` 读目标窗口那块（原图坐标，不缩图）。
另外有些窗口会直接拒绝 `PrintWindow`（返回 False、存出来是几百字节空白图）—— 见到 `PrintWindow=False`
立刻换全屏抓取，不要重复试 flag。

**目标窗口太窄/被别的窗口遮住时读不到数值列**：传感器窗口的“当前/最小/最大”列常在右侧，
窗口被拉到几百像素宽就只剩标签。这时结论只能是“没读到”，**不能**写成“该工具不显示 X”；
正确的下一步是让用户把窗口拉宽/拖出遮挡区再截一次。

要截的是**必须以管理员身份运行**的程序（HWiNFO 传感器、硬件工具）时，得先有个提权通道 ——
通道怎么搭、以及“cmd 自删 / LastTaskResult 假成功”这三个坑见 `references/elevated-oneoff-cmd.md`。

## 2. OCR（WinRT，离线、无需第三方包）

现成脚本：`D:\hermes-test\ocr2.ps1`，用法
```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:/hermes-test/ocr2.ps1" \
  -img "D:\path\to.png" -out "D:\hermes-test\ocr-out.txt"
```

三个必须记住的点：

1. **先加载 `Windows.Globalization.Language` 类型**，否则 `New-Object Windows.Globalization.Language('zh-Hans-CN')` 报
   `TypeNotFound`：
   ```powershell
   [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null
   ```
   其余要预加载的：`Windows.Storage.StorageFile` / `Windows.Graphics.Imaging.BitmapDecoder` /
   `Windows.Media.Ocr.OcrEngine`。异步要用 `[System.WindowsRuntimeSystemExtensions]` 的 `AsTask` 泛型反射包一层（照抄脚本即可）。
2. **`zh-Hans-CN` 引擎认英文标签没问题**（本机可用语言 `en-US, zh-Hans-CN`），一个引擎够用。
3. **结果写到 UTF-8 文件，用 `read_file` 看** —— 直接 print 到 terminal 时中文经 bash 的 GBK 解码会变成
   `��`，看起来像识别失败，其实文件是好的。

## 3. 提高准确率

- 密集 UI 先 2x 双立方放大再 OCR（`System.Drawing` 的 `HighQualityBicubic`），行数会明显更全。
- 典型误识：`|`→`1`、`±`→`��`、`I`→`l`、`0`→`O`。**数字要按下标格式反推**：
  `59303 MB/s`、`2970.2 MHz`、`28-35-35-76` 这类含小数点/横杠的字段，单独出现的裸数字多半被吃了小数点。
- OCR 只按**行**输出，同一行里的多列（表格）会被拆散或拼错顺序 —— 把“标签行 + 数值行”成对读，别按 OCR 顺序硬配。

## 4. 抓不到的部分，别硬编

- 固定尺寸窗口 `SetWindowPos` 改不大小（实测 `414x623` 的 ZenTimings 设 780x1020 无效）→
  窗口外的行**根本不在图里**，OCR 不会“漏读”，它只是拍不到。判断方法：OCR 出来的行数与该窗口
  一屏能显示的行数吻合，就是被裁掉了，需要滚动/换工具，不要猜值。
- 免费版 HWiNFO 每次启动有「仅限非商业使用」倒计时弹窗，不点 Continue 就不会进传感器窗口；
  它的 `-r/-c/-l` 报告与日志参数是 **Pro 授权功能**。所以要么让用户点一下再截，
  要么改用不弹窗的工具（ZenTimings 的时序表可直读，主窗口顶部三行含 MCLK / FCLK / UCLK）。

## 6. `vision_analyze` 报 404 model_not_found = 配置回落到一个池子里不存在的默认模型

症状：`404 - {'error': {'code': 'model_not_found', ... 'gemini-3.8-flash-medium'}}`，而中转池 `/v1/models` 里根本没有 gemini。
根因不是池子不支持识图，而是 `auxiliary.vision` 配成 `provider: auto` + `model: ''` 时会回落到写死的默认模型名。

修法（**不要直接改 `config.yaml`：它对 agent 只读，patch/write_file 会被拒**，走 CLI）：

```bash
hermes config set auxiliary.vision.provider <pool-provider>        # 例如 ianlee
hermes config set auxiliary.vision.model    <vision-capable-model> # 例如 deepseek-v4.1-flash
```

改完热生效，不用重启，立刻拿用户那张图重试即可。

**先验证模型真有视觉再改**：`/v1/models` 里 `supports_images: true` 不保证上游真接图。用自己画的一张测试图
（`System.Drawing` 写字 → `image_url: data:image/png;base64,...`）打一次 `/v1/chat/completions`，能读出图里的字才算。
同一批测多个候选模型，取真能读的那个写进配置。

## 5. OCR 只是降级手段，结论必须复核

- **能识图时先让 `vision_analyze` 读整张图**，OCR 只用于模型没有视觉能力时的兜底。OCR 会把密集表格的整行吞掉
  或串列，而“少了一行”看起来极像“这个窗口没有这一项”——本机就据此得出过「ZenTimings 主窗口不含 FCLK」的错误结论，
  实际顶部三行就写着 FCLK/MCLK/UCLK，vision 一眼看到。
- 因此：**凡要写下“某工具/某窗口不显示 X”这类结论，先用另一条路径复核**（vision_analyze 同一张图、官方文档、
  或确认窗口是否可滚动），再写进 skill 或告诉用户——这类结论一旦进 skill，会误导后面每一个会话。
- OCR 出的数字对不上预期时，**先怀疑 OCR，再怀疑硬件**：小数点被吞、列顺序被重排是常态。

