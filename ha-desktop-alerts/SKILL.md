---
name: ha-desktop-alerts
description: "Use when 门铃/摄像头/传感器等设备事件要弹到电脑桌面(弹窗+声音+常驻监听)。"
version: 1.0.0
author: 50.110 bot
license: MIT
platforms: [windows]
tags: [home-assistant, alerting, popup, doorbell, camera, websocket]
metadata:
  hermes:
    tags: [home-assistant, alerting, popup, doorbell, camera, websocket, 门铃]
    triggers: ["门铃", "按门铃", "有人逗留", "摄像头报警", "弹到电脑", "电脑有画面",
              "HASS.Agent", "桌面弹窗", "事件驱动提醒", "摄像头有人"]
---

# 设备事件 → 电脑桌面弹窗

当用户要"有人按门铃/摄像头看到人 → 电脑上出画面",而不是手机推送时用本 skill。

**核心判断:不要为这个需求装 HASS.Agent,也不需要 MQTT。** HASS.Agent 只负责把通知弹到
Windows,不负责取设备画面;而本机就住着 Hermes,自己订阅 HA 事件 + 弹窗更直接可控。
HASS.Agent 真正的价值在**反向**(把电脑状态喂给 HA、用 HA 控制电脑音量/媒体)。

## 固定流程

### 1. 先把"事件源"找出来(最花时间的一步)

在 HA 里找:

- `config/entity_registry/list`(WS)—— **含 disabled 实体**,`/api/states` 看不到被禁用的;
  `config/device_registry/list` —— 按 manufacturer/model 过滤找候选设备(门锁/摄像头/门铃)
- 找“按钮/事件”类:某设备是否只暴露了 `button.*_info`(说明**按键事件根本没接进 HA**,
  例如米家无线开关);此类设备不能当触发源。
- **米家设备看云端消息实体**:`xiaomi_miot` 会把米家云的通知落成
  `sensor.mi_<uid>_message`(state = "设备名: 时间 事件",attributes 里有 `room_name`/`event`/
  `device_id`/`timestamp`/`entity_picture`)。米家门锁的门铃 = **`event: 7.1006`**,
  实测从按铃到实体更新 **约 1 秒** —— 足够快。
- 具体设备的服务/属性/事件清单查
  `https://miot-spec.org/miot-spec-v2/instance?type=<urn:miot-spec-v2:...>`
  (比翻 HA 本地缓存快,而且本地缓存文件名含 `:` 在 Windows 侧打不开)。
- 米家账号里到底有哪些设备:见 `references/ha-mihome-event-sources.md` 的 `/home/device_list`。

### 2. 订阅事件(常驻)

```python
ws://<ha>:8123/api/websocket → {"type":"auth",...} → {"id":1,"type":"subscribe_events","event_type":"state_changed"}
# 事件里按 entity_id 过滤,再对 state/attributes 做关键词判定
```

- 必须带**断线重连**(`except → sleep 5 → 重连`),这类服务要能自己活几个月。
- 判定用**结构化字段优先**(`event` 代码 / `room_name` / `device_id`),关键词正则只当兜底。

### 3. 弹窗 + 声音(两路一起交)

置顶无边框窗、右下角、**自动关**(20~25 秒)、点一下/ESC 关、自制 wav 提示音、每条事件写日志。
写法与开机自启(VBS 静默启动 + 启动文件夹快捷方式)见 skill **`windows-strong-reminders`**。

**默认就交两路**(用户明确要过"弹窗 + 系统通知"两个都要):① 自己的置顶大弹窗当主力(不受系统通知
设置/免打扰影响);② Windows 原生 Toast 当兜底(进通知中心,错过还能翻到,可带图)。
Toast 的零依赖写法、验证方法与"全屏时横幅被静音"那条坑,见
`references/windows-toast-alerts.md`(现成脚本 `templates/toast.ps1`)。

### 4. 有没有"画面"—— 先验证消息带不带图,再谈方案

- 事件消息可能带图:集成会把图 URL 落到 `entity_picture` / `img_url`(摄像头类报警带图,
  **门锁门铃类往往纯文字**)。判定方法:拉起监听后让用户实际触发一次,看日志里 `entity_picture` 是否为空。
- **能取图的只有已经在 HA 里存在的摄像头实体**(`/api/camera_proxy/<camera_entity>` 直接拿 JPEG)。
- 拿不到画面的三条路(按推荐序):
  1. 门口/门铃另行接入一台 HA 能取流的摄像头(最稳,取图链路已验证);
  2. 厂商官方集成(订阅厂商云 + 可能带出摄像头实体);
  3. 自实现厂商云"看家/报警快照"接口(能成但不保证,需要云鉴权签名)。
- 门锁自带的猫眼摄像头常**不会**被 "xiaomi_miot" 类集成映射成 camera 实体 → 不要假设它可用;
  门锁也多不支持 HA 远程开锁(只有蓝牙近场动作),别做"通知里带开门按钮"。

### 4b. ✅ 门锁摄像头的画面可以取到（2026-09-13 实测打通）

**别急着买摄像头**：米家智能门锁（`xiaomi.lock.s1` 小米智能门锁 4 Pro 实测）的猫眼/门外摄像头
画面**能从米家云取到**，包括『有人按门铃』那一帧：

1. `business.smartcamera.api.io.mi.com/common/app/get/eventlist`（带 `doorBell=true`）
   → `thirdPartPlayUnits[].eventTypeDetail[]`，挑 `event == "Bell"` 那条，取 `imgStoreId` + 外层 `fileId`
2. `processor.smartcamera.api.io.mi.com/miot/camera/app/v1/img`（rc4 签名 + `yetAnotherServiceToken`）
3. 返回的是 **AES-CBC 加密的 JPEG**：`key = base64decode(ssecurity)`、`iv = segmentIv`，解出来才是图

云鉴权用 `/config/.storage/xiaomi_miot/auth-<uid>-cn.json`（sid=xiaomiio；micoapi 那份 401）。
完整调用代码/签名细节/坑 → `references/mihome-lock-cloud-snapshot.md`，现成脚本 `templates/mi_snapshot.py`。

- 事件上云有 **5~15 秒延迟** → 监听程序要重试轮询，并**先弹文字、图到了再弹带图的**
  （同窗口替换 + Toast 同 Tag 覆盖，不要堆一屏）。
- 用户说"画面不对（显示的是别的摄像头）"，先查是不是**触发词太宽**导致别的摄像头的消息也被当成门口
  → 按 `device_id`/`model` 分流：门锁走门口抓拍，其它设备单独标注设备名/房间。

### 5. 验证(不靠"应该弹了")

- 服务端:读日志找回执(连接时间、每条消息、是否弹窗、是否带图)。
- 界面:不登 HA 也能看 —— `computer_use` 抓本机窗口/浏览器截图,再用 numpy 量像素
  (卡片或窗口真实尺寸、是否被压扁)。
- ⚠️ `computer_use` 抓屏只抓**前台窗口**,系统 Toast 等覆盖层不在其中 → **看不到横幅 ≠ 没发出去**;
  投递用 Toast 历史条数证明,整屏截图要自己用 System.Drawing 抓(见
  `references/windows-toast-alerts.md`)。
- **只看事件监听不等于成功**:要让用户实际按一次门铃,日志里出现"已弹窗"才算通路。

## Pitfalls

- ⚠️ **"全屏应用"会静音通知横幅**,而 agent 自己驱动桌面的进程(cua-driver.exe 等)常被系统判成
  全屏应用 → 于是通知条数在涨、横幅就是不出现。别据此改代码;先看
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Notifications\QuietHours` 的
  `FullScreenProcess` / `QuietHoursServiceState`,并用 Toast 历史条数证明已投递。
- ⚠️ **单一事件源不保证每次触发**:同一个门铃短时间重复按,厂商云消息可能被合并/不推;
  重要场景要配第二触发源(如一盏 HA 能看到的灯/插座做 relay),并在交付时明说这个限制。
- ⚠️ 触发链条涉及厂商云时,延迟取决于厂商云端;实测 1 秒可以接受,但不要宣传成"实时"。
- ⚠️ 弹窗程序不要用 `MessageBox`(无人点击会永久挂住);用可自动关的置顶窗。
- ⚠️ 用户说"有个文字提醒"时分清是谁弹的:自己的日志里有"已弹窗"才是自己弹的,
  否则可能是手机 App/设备本身的提示 —— 不要冒领成果。

## 相关

- Windows 弹窗/常驻服务/开机自启/计划任务提权 → skill `windows-strong-reminders`
- HA 接口总则(地址/token/WS 读写/仪表盘) → skill `home-assistant-api`(用户自有)
- 米家云接口细节(设备列表、属性读写、消息实体字段) → `references/ha-mihome-event-sources.md`
- Windows 投递层(原生 Toast 写法/验证/全屏静音坑/watcher 重启) → `references/windows-toast-alerts.md` + `templates/toast.ps1`
