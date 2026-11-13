---
name: home-assistant-ops
description: Use when touching Home Assistant (HA) on the LAN.
author: 50.110 bot
platforms: [windows, linux, macos]
tags: [home-assistant, home-automation, api-token, lan, smart-home]
metadata:
  hermes:
    triggers: ["home assistant", "HA", "192.168.50.206:8123", "50.206",
               "hass token", "HASS_TOKEN", "HASS_URL", "long-lived access token",
               "长期访问令牌", "控制灯", "开关", "传感器", "实体", "entities",
               "/api/states", "homeassistant platform plugin", "HA 能不能控制"]
    related_skills: [unraid-server-ops, go2rtc-camera, openhue]
---

# Home Assistant Ops (HAOS VM @ 192.168.50.206:8123)

HA runs as a VM on the Unraid box. **Host/VM-layer problems (VM paused, cache full,
wrong HAOS image, VM unreachable) are NOT this skill — go to `unraid-server-ops`**
(its sections 「VM 被 QEMU 自动暂停」、「VM shows running but unreachable」、
「HAOS VM image mismatch」). This skill is the application layer: is HA up, can I
talk to its API, how do I get access.

## Address rule (cost a dead end the first time)

ALWAYS write the full `192.168.50.206`. The shorthand `50.206` is parsed as the
legal IPv4 address `50.0.0.206` by every native tool, so the probe silently goes to
a public address and times out — looking exactly like "HA is down". Same for `.1`,
`.5`, `.161`. Windows `ping` normalizes the value to `50.0.0.206` in its output:
that echo is the tell that you typed a shorthand.
- ⚠️ 提示或通知里若出现 `192.168.50.26`，通常是通知标题或用户手快漏打了 `0`（实际对应 `192.168.50.206`），勿直接认定为新设备，先探测 `192.168.50.206`。

## Probe ladder (verified from 50.110)

```bash
H=192.168.50.206
curl -s -o /dev/null -w "http=%{http_code}\n" -m 8 http://$H:8123/          # frontend
curl -s -m 8 http://$H:8123/ | grep -o '<title>[^<]*</title>'               # <title>Home Assistant</title>
curl -s -m 8 http://$H:8123/manifest.json | head -c 120                     # PWA manifest
curl -s -m 8 http://$H:8123/api/                                            # 401: Unauthorized
```

| Result | Meaning | Next step |
|---|---|---|
| root `200` + `<title>Home Assistant</title>` | frontend up | — |
| `/api/` → `401: Unauthorized` | HA **is** alive; you simply hold no token | get a token (below) |
| `/api/` → JSON with a `message`/entities | token already wired somewhere | reuse it, don't ask again |
| root times out / refused | host/VM layer | `unraid-server-ops`: `virsh list --all` (paused?), cache full, QEMU IO error |

Do NOT report a frontend 200 as "能控制"— a live web UI says nothing about API
access. State plainly which of the two you actually verified.

## Getting API access

1. **Look for an existing credential before asking** — never ask for one that is
   already stored: `grep -i hass ~/AppData/Local/hermes/.env` (key names only),
   gbrain pages under `credentials/*` / `concepts/net-topology`,
   `browser_vault_list` for a saved HA login. All empty → ask.
2. **Ask the user to mint a long-lived token**: HA web UI → bottom-left profile →
   安全 → 长期访问令牌 → 创建. It is a credential: store it immediately per the
   user's standing rule (`gbrain put credentials/...`, or as `HASS_TOKEN` in
   `~/AppData/Local/hermes/.env` alongside `HASS_URL=http://192.168.50.206:8123`).
   Never echo it into chat, never `export` it from agent-side code, and don't ask
   the user to paste it in the chat — ask for it to be written to the store.
3. **Never drive the HA login page with browser automation and never invent
   credentials** — a login wall means stop and ask. (User rule: 登录墙链接直接请
   用户提供，别烧 token 跑浏览器自动化。)
4. **Hermes already ships the platform plugin**:
   `~/AppData/Local/hermes/hermes-agent/plugins/platforms/homeassistant/`
   (`kind: platform`; `requires_env: HASS_TOKEN`; `optional_env: HASS_URL`,
   default `http://homeassistant.local:8123`). With those two set it subscribes to
   the HA WebSocket event bus (per-entity cooldowns / domain filters), delivers
   outbound messages as HA persistent notifications, and supports out-of-process
   cron delivery via the `notify.notify` service (depends on the notify integration
   being configured).

## Talking to the API once a token exists

```bash
curl -s -H "Authorization: Bearer $HASS_TOKEN" http://192.168.50.206:8123/api/          # message + version
curl -s -H "Authorization: Bearer $HASS_TOKEN" http://192.168.50.206:8123/api/states    # all entities
curl -s -X POST -H "Authorization: Bearer $HASS_TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id":"light.x"}' http://192.168.50.206:8123/api/services/light/turn_on
```

Read raw JSON (grep / python) — do not assume entity_ids; list `/api/states` first
and pick the real ones before sending a service call. **Success = the new state read
back from `/api/states`, not a 200 from the service call.**

## Mijia/Xiaomi cloud: the back doors are stronger than the entities

With the HACS `xiaomi_miot` integration configured, three routes reach things HA has
no entity for — full recipes in **`references/xiaomi-miot-cloud-api.md`**:

```python
# 1. call any Mi-cloud API through HA (needs only the HA token)
POST http://<HA>/api/services/xiaomi_miot/request_xiaomi_api?return_response=true
{"entity_id":"<any entity of that Mi account>", "api":"/home/device_list",
 "data":{"getVirtualModel":true,"getHuamiDevices":1}, "method":"GET"}
# → resp["service_response"]; WITHOUT ?return_response=true you get [] and think the API is empty
# 2. read/write any miot property
api=/miotspec/prop/get, data={"params":[{"did":..,"siid":..,"piid":..}]}
# 3. the Mi-cloud message feed (doorbell presses, unlocks, camera alarms, feeder logs)
entity: sensor.mi_<user_id>_message   → attrs title/content/room_name/event/entity_picture
```

- **`sensor.mi_<uid>_message` is the only reliable trigger source for Mi-Home events
  that never become HA entities** (e.g. a lock's “有人按门铃”). Subscribe to its
  `state_changed`; it carries the device name, room, event id and timestamp within
  seconds.
- It is **not** 1:1 with reality: repeated presses in a short window get coalesced by the
  cloud, and a device's doorbell message usually carries **text only** (`entity_picture`
  empty). Don't promise a picture from it — see the popup reference for image sources.
- Device capabilities (services / properties / events) come from
  `https://miot-spec.org/miot-spec-v2/instance?type=<urn>` — HA's local spec cache
  lives at `/config/.storage/xiaomi_miot/urn:miot-spec-*.json` and **its colon in the
  filename makes it unopenable from Windows** (listdir works, open/copy fails).
- Never echo device `token` / cloud `ssecurity` values: the device-list response and
  `/config/.storage/xiaomi_miot/auth-*.json` both contain credentials.

## HA events → a Windows popup (no HASS.Agent, no MQTT)

Subscribe to the trigger over the HA WebSocket, fetch a picture, show a tkinter window —
recipe and pitfalls in **`references/ha-events-to-windows-popup.md`**. Works from an
agent-started background process; verify it landed by capturing the window with
`computer_use`, not by asking the user what they saw.

## When the user cannot describe a visual problem: look at the screen yourself

Do not ping-pong descriptions ("上面一条"…"还是不对"…). This machine's `computer_use`
can capture the browser window the user is actually looking at, and dashboard saves
propagate live — so "change it, screenshot it, measure the pixels with numpy" is the
fastest closed loop (that is how the `aspect_ratio` bug was pinned: measured card
401×25 px = ratio 16.04 = width/16).

- The current local model **already sees images** — never suggest “switching to a
  multimodal model”; just look (`vision_analyze`, `computer_use`).
- Placement/room-assignment work: **do it yourself from the available reference**
  (derive rooms from the 2D floor plan, positions from the option images) and let the
  user fine-tune afterwards. Do not ask the user to drag/describe what you can derive.
- “跟着 X 改” means **regenerate against X's coordinates**, not translate the old asset.
- Dashboard / `picture-elements` mechanics (a card squashed to a thin strip by
  `aspect_ratio: "16/9"`, `panel: true` full-screen behaviour, storage dashboards being two
  independent copies that must both be edited, the local drag editor, per-light glow
  overlays) live in the sibling skill **`home-assistant-api`** — load it before editing
  dashboards.

## 「设置里有 N 个更新但装不上」

`设置 → 更新` 列表就是 `update.*` 实体里 `state == on` 的那些 —— `/api/states` 一拉就能数出
真实待更新数(addon 与 Marketplace/自定义卡片共用 `update.` 命名空间)。

- **失败原因只能从调用返回里读,不能猜**:`POST /api/services/update/install {"entity_id":"update.x"}`
  成功返 200/列表,失败返 **500 且 body 的 `message` 就是真因**。服务调用错误不进 HA 通知,
  前端只丢一句模糊提示,所以用户转述成「说要重启」时不要照着去重启 —— 先复现那一步拿 message。
- 2026.11 起 HACS 并入内置 Marketplace:最常见的两个 500 是「市场首次警告未接受(按用户)」和
  「仓库缺 `hacs.json`」。完整处理(接受警告、侧载、`update.skip` 跳版、重启后验证)在
  **`home-assistant-api`** 的「HA 2026.11 起 HACS 变成内置 Marketplace」一节。
- `hassio.addon_update` 已不存在(调用 400);addon 更新同样走 `update/install`。

## 「不可用实体数」为什么天然翻倍 —— 同一小米账号登了两次

本机 `.storage/core.config_entries` 里有 **两个 `xiaomi_miot` 配置项**，title 都是
`Xiaomi: 1291104493`（同账号、不同 entry_id，第二份多了 `filter_models`/`trans_options`），
于是**每个设备被暴露成两份**：`light.lemesh_wy02_8491_light` 与 `..._light_2`。
实测 1137 个注册实体里 498 个属于这两个 entry（250 + 248），`/api/states` 里
不可用的 16 个 = **8 台设备 × 2**。

- 判断是否重复：`/api/states` 里同名成对出现（一份带 `_2`）；精确对法 = 两个 entry_id 之外
  的 `unique_id` 部分完全相同（`<MAC>-<entry_id>-<index>`）。
- ⚠️ **不要随手删掉其中一个 entry**：base 与 `_2` 归属是**混的**（实测有的设备 base 属旧 entry、
  有的属新 entry），删任一份都会让一批 `entity_id` 消失。**正确姿势 = 删「引用少的那个」+ 把配置里
  指向被删名字的引用改指幸存名字；只要幸存者名字在配置里被引用得少，就能把改动压到最小。**
- ⚠️ 删 entry 前必须先算清「配置文件到底引用了哪些实体」，**别用 `/api/states` 或
  `core.restore_state` 当引用源**（它们包含全部实体，会把 57 条真实引用放大成 465 条，结论完全相反）。
  真实引用源只有：`configuration.yaml` / `automations.yaml` / `scenes.yaml` / `scripts.yaml` /
  `button_card_templates.yaml` / `dashboards/*.yaml` / `.storage/lovelace.*`。

### 去重复 entry 的已验证流程（2026-11-13 实测：572→324 实体，不可用 16→8）

```bash
# 0) 快照（本地 + HA 内各一份，HA 内那份放 /config/.hermes-backup-<date>/.storage/）
#    core.config_entries / core.entity_registry / core.device_registry / lovelace.* / scenes.yaml / dashboards
# 1) 算引用：遍历上面那 7 类文件，取所有 {domain}.{object} token 里属于 xiaomi_miot 的集合；
#    按 config_entry_id 分组 → 得到「每个 entry 被引用了多少个实体」
#    （实测 44 vs 13 → 删 13 的那份）
# 2) 对每个被引用且将被删的实体名，找它的 twin（unique_id 去掉 config_entry_id 后相同）：
#      twin 名是「不带后缀的基名」而将删的是 `_2` → 改配置文本（文本替换）
#      twin 名是 `_2` 而将删的是基名       → 先删 entry（腾出基名）再 WS 改名 twin → 基名（配置零改动）
# 3) 删 entry（REST，返回 {"require_restart":false}）：
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "http://<HA>/api/config/config_entries/entry/<entry_id>"
# 4) storage 模式仪表盘**不能改文件**（HA 内存里有副本，改文件既不生效又会被覆写）→ 走 WebSocket：
#    {"type":"lovelace/config","url_path":"lovelace"} 取 → 递归替换字符串 → 
#    {"type":"lovelace/config/save","url_path":"lovelace","config":...}
#    ⚠️ url_path 不等于 id：3d_plan 的 url_path 是 "3d-plan"、xiaoshi_test 是 "xiaoshi-test"
# 5) 改实体名同理走 WS：{"type":"config/entity_registry/update","entity_id":"old","new_entity_id":"new"}
# 6) 场景热加载：POST /api/services/scene/reload（200 即可）
```

验收（缺一条都别收工）：
```bash
# 实体数：states 572→324、registry 1137→889、unavailable 16→8（正好减半 = 每台设备只剩一份）
# 只剩一个 xiaomi_miot entry 且 state=loaded
curl -s -H "Authorization: Bearer $TOKEN" http://<HA>/api/config/config_entries/entry
# 三个仪表盘 WS get 全部 success=true；配置里引用的实体逐个在 /api/states 里存在
```
⚠️ 验收时「配置里引用的实体不存在」要先分清**本次引入**还是**历史遗留**：本次改动前先把
`/api/states` 抓一份存好，改完对比 `pre` 集合即可（实测 8 条缺失全是删除前就已不存在的旧卡片：
`loock_t1pro`、`xiaomi_rd08`、`sensor.weather_aqi_daily`）。
⚠️ 回滚面：被删 entry 的实体/设备注册项一起消失，只能**停机**后把 `.storage` 快照换回去（或重新在
UI 加一次集成）——所以第 0 步的快照是唯一的 undo。
- 因此**告警判据要按设备去重**再比：50.161 的 `~/.hermes/scripts/ha_daily_check.sh`
  已改成「`_2` 结尾且同名 base 也在不可用集合里时只数 base」，并加了绝对下限
  `HA_UNAVAIL_FLOOR`（默认 20）：基线只有 8 台时，任何一两个设备抖动都会让旧版
  「比中位数 +30%」规则天天误报。趋势文件改记 `logs/ha-unavailable-history-v2.txt`，
  状态行现在同时打印 `不可用(去重)/原始/下限/中位`。

### 判读这类告警（2026-11-12 08:00 的 28/15 实例）

「不可用实体突增」在小基线 + 重复 entry 的机器上基本都是**小米云设备掉线**，不是 HA 故障：

- 先确认 HA 本身：`/api/` 是否 200、`/api/states` 实体总数（本机 572）。
- 再点名：把不可用实体按 `friendly_name` 列出来，几乎全是 `xiaomi_miot` 云设备
  （LeMesh 凌动开关 / 米家人体 / 小米家庭屏 / aimore 灯）。它们超时靠云端 list 判在线，
  设备断电、传感器没电、开关掉零线就 `unavailable`，且**掉一台 = 两个实体**。
- 反查某天到底哪几台掉了：HA 的 history API 一次只能带 `filter_entity_id`（不带就报
  `filter_entity_id is missing`），按 40 个一批喂进去，用
  `/api/history/period/<start>?end_time=<end>&minimal_response&no_attributes&filter_entity_id=a,b,c`
  再按时间点回放状态；URL 里的 `+08:00` 必须写成 `%2B08:00`，否则 `+` 被当空格、
  接口回一条 `message`。
-  chronically 离线的设备（本机 4 天未恢复）：`lumi_bmgl01_d6d3`（米家人体 2 的光照/触发）、
  `light.lemesh_wy02_2711_*`（天井灯）、`switch.xiaomi_x10a_99ed_*`（家庭屏闹钟）、
  `light.xiaomi_03_865b_indicator_light`（人在传感器指示灯）。这类是**物理侧**问题：
  去米家 App 看设备在线状态 / 查电池与开关供电，HA 侧无解。

## Pitfalls

- ❌ Probing `50.206` / `50.1` shorthand → see Address rule above.
- ❌ Declaring HA "fine" from a frontend 200 while the API is 401 — 可见 ≠ 可控制;
  report the distinction.
- ❌ Hunting a token by grepping the whole home dir or the gbrain PGLite dir —
  recursive grep over `~/.gbrain/brain.pglite` hangs to the tool timeout. Use
  `search_files` scoped to text paths (`~/.hermes/...`) or the gbrain CLI.
- ❌ Answering "能不能控制" from memory of past sessions — run the probes.
- ❌ Asking the user for an SSH/root password when the HA question only needs an API
  token — HA access is token-based; root console access is an `unraid-server-ops`
  (`virsh console`) concern.
