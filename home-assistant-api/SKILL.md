---
name: home-assistant-api
description: Use when reading or controlling Home Assistant entities.
version: 1.0.0
author: 50.110 Windows bot
platforms: [windows, linux, macos]
tags: [home-assistant, smart-home, api, credentials]
metadata:
  hermes:
    triggers: ["HA", "Home Assistant", "智能家居", "开灯", "窗帘", "空调", "摄像头",
               "你能看见 HA 吗", "8123", "小米米家", "homeassistant"]
---

# Home Assistant API 接入与操作

ianlee168 家里的 HA = Unraid 上的 KVM VM(HAOS,2vCPU/2GB),通过 REST + WebSocket API 操作。
本 skill 管怎么接、怎么读、怎么写、怎么验证。

**读接口随便用,动真实设备(灯/窗帘/空调/锁)前先问用户。**

## 地址:必须写全

把 `50.206` 这类**两段简写**丢给 curl / 浏览器会被解析成另一个 IP(实测踩过,直接超时),
**永远写全四段**(例:`http://<HA_IP>:8123/`)。

- 默认端口 **8123**(用户常少写 3,记成 812)。
- `401` = 实例在跑、但请求没带 token;**连不上**先确认 VM 是否被暂停(cache 盘满 → QEMU 自动暂停 VM)
  或 IP 是否漂移(DHCP 未绑定),再怀疑服务。

## 令牌位置(不要问用户要第二次)

| 位置 | 用途 |
|---|---|
| gbrain `credentials/home-assistant` | 权威副本(长期访问令牌) |
| 本机 Hermes `.env` → `HASS_URL` + `HASS_TOKEN` | Hermes 平台插件用 |

取了就走 env 变量 / `Authorization: Bearer`,**别 echo、别贴回聊天**(硬编码凭证也是仓库红线)。

拿不到时:让用户在 HA 左下角头像 → 安全 → 长期访问令牌 → 创建,拿到后**立刻存 gbrain**。

## 快速验证(先查证再答)

```bash
curl -s -o /dev/null -w '%{http_code}\n' "$HASS_URL/api/"            # 401 = 活着但没带 token
curl -s -H "Authorization: Bearer $HASS_TOKEN" "$HASS_URL/api/"     # {"message":"API running."}
curl -s -H "Authorization: Bearer $HASS_TOKEN" "$HASS_URL/api/config" | head -c 200
```

- `/api/states` — 一次拉全部实体(配合 python 数域分布)
- `/api/services` — 拉可调用的服务(域 → 服务名)
- `/api/config` — 版本 / 站点名 / 已加载组件

## 最小 Python 客户端

```python
import os, json, urllib.request

BASE  = os.environ["HASS_URL"].rstrip("/")
TOKEN = os.environ["HASS_TOKEN"]

def api(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))
```

## 写入后必须回读验证

服务调用返回 `200`/`[]` **只说明 HA 接受了请求**,不等于有可观察效果。

- ❌ 别拿 `persistent_notification.create` 的 200 当证据:该通知**不落成 state 实体**,
  `/api/states` 里查不到(2026.9.2 实测,实体总数前后不变)。
- ✅ 回读该通知要用 **WebSocket**:

```python
ws://<HA_IP>:8123/api/websocket
# 收 {"type":"auth_required"}
# 发 {"type":"auth","access_token":TOKEN} → 收 {"type":"auth_ok"}
# 发 {"id":1,"type":"persistent_notification/get"} → result 列表
```

- 控制类实体改状态后,回读 `/api/states/<entity_id>` 核对 `state` + `last_changed`。
- WS 通道还能做 REST 没有的事(订阅 `state_changed`、查注册表);反向代理下的 HA 若开了
  `use_x_forwarded_for`,注意 WS 也要走同样的 header。

## 家底快照(2026-09-13 实测)

- HA 2026.9.2,**568 实体 / 62 服务域 / 271 服务**
- light 46 / switch 103 / cover 4 / climate 3 / camera 3
  / media_player 7(小米家庭屏×2、8 寸屏、中控屏)/ automation + scene + script 可触发
- 手机推送:`notify.mobile_app_*` 多个 → **HA 能直接往用户手机推通知**
  (设备侧通道,可与微信 / telegram 推送互为保险)
- 组件:`xiaomi_miot`(米家全家桶)、`hassio`(Supervisor)、`mobile_app`、`notify`

数字只用来说明量级,**要真实数字就现拉 `/api/states` 数**(先查证再答)。

## 401 会在 HA 里留一条通知

未带 token 探测 `/api/` → HA 记一条 `Login attempt failed` 通知(来源是本机主机名)。
看到别慌 —— 多半是 agent 自己探活留下的,可顺手 dismiss。

## Hermes 侧接入(需启用插件 + 重启 gateway)

插件 `plugins/platforms/homeassistant` 是 **bundled 但默认不启用**的 —— 只重启 gateway 没用:

```bash
hermes plugins enable homeassistant-platform --no-allow-tool-override   # 先启用("Takes effect on next session")
hermes plugins show homeassistant-platform                              # Status 应为 enabled
hermes gateway restart                                                   # 再重启
hermes gateway status                                                    # 看新 PID
```

- **启用前确认依赖**:插件要 `aiohttp`(bundled venv 里通常已有,`python -c "import aiohttp"` 验)。
- **重启 gateway 不一定断开你的桌面会话**:desktop 的 chat 后端可能是另一个进程
  (`hermes_cli.main serve --host 127.0.0.1 --port 0`),而 gateway 是计划任务 / 服务 ——
  先 `Get-CimInstance Win32_Process`(Windows)或 `ps` 分清两边,再决定要不要提醒用户掉线。
- 成功判据(`logs/gateway.log`):`Connecting to homeassistant...` → `[Homeassistant] Connected to <url>`
  → `✓ homeassistant connected` / `Gateway running with N platform(s)`。
- ⚠️ **事件转发默认是关的**:没配 `watch_domains` / `watch_entities` / `watch_all` 时日志会报
  `All state_changed events will be dropped` —— 连上是连上,但什么都不转发。配置写在 gateway HA 平台
  的 `extra`:`{url, watch_domains[], watch_entities[], ignore_entities[], watch_all, cooldown_seconds(默认 30)}`。
  别为了"接上"就开 `watch_all` —— 家里几百个实体会把 agent 淹掉。
- **出站两条路不同**:在线 adapter 的 `send()` 用 `persistent_notification.create`(标题固定 "Hermes Agent",实测可用);
  **离线/cron 投递**(standalone sender)走 legacy `notify.notify` + `target=<chat_id>` ——
  2026.9.2 实测非设备 target(`notify` / `persistent_notification` / 编造名)全部 **HTTP 500**,
  只有 `mobile_app_<device>` 这类设备 target 才有戏;要在 cron 里推 HA 通知,先实测确认再写进 job。

不重启也能干活:直接用上面的 REST/WS 手动读写。

## 相关

- HA 备份加密密码 / HAOS 换盘迁移 / VM 救援 → skill `unraid-server-ops`
- 摄像头(go2rtc / Frigate)→ skill `smart-home/go2rtc-camera`、`smart-home/frigate-detection`
