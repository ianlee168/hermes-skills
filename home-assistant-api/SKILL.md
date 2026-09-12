---
name: home-assistant-api
description: Use when reading or controlling Home Assistant entities.
version: 1.0.0
author: 本机 bot (<THIS_HOST>)
platforms: [windows, linux, macos]
tags: [home-assistant, smart-home, api, credentials]
metadata:
  hermes:
    triggers: ["HA", "Home Assistant", "智能家居", "开灯", "窗帘", "空调", "摄像头",
               "你能看见 HA 吗", "8123", "小米米家", "homeassistant"]
---

# Home Assistant API 接入与操作

用户家里的 HA = Unraid 上的 KVM VM(HAOS 18.2,2vCPU/2GB,MAC 52:54:00:cc:8b:ec)。
本 skill 管怎么接、怎么读、怎么写、怎么验证。

## 地址:必须写全 4 段

❌ `curl http://50.206:8123/` → Windows 把 `50.206` 解析成 IP **50.0.0.206**,超时。
✅ `http://<HA_HOST>:8123/` —— 本机(<THIS_HOST>)与 HA 同网段。

- 内存里的 `50.206` 只是简写,**发请求时永远补全 <HA_HOST>.**
- 401 = 实例在跑、但请求没带 token;连不上时先跑 ping <HA_HOST> 再怀疑服务。

## 令牌位置(不要问用户要第二次)

| 位置 | 用途 |
|---|---|
| gbrain `credentials/home-assistant` | 权威副本(长期访问令牌) |
| `C:/Users/ianle/AppData/Local/hermes/.env` → `HASS_URL` + `HASS_TOKEN` | Hermes 插件用 |

取了就用 env 变量 / `Authorization: Bearer`,**别 echo、别贴回聊天**(参考铁律)。
拿不到时:让用户在 HA 左下角头像 → 安全 → 长期访问令牌创建,拿到后立刻存 gbrain。

## 快速验证(先查证再答)

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://<HA_HOST>:8123/api/
curl -s -H "Authorization: Bearer $HASS_TOKEN" http://<HA_HOST>:8123/api/
curl -s -H "Authorization: Bearer $HASS_TOKEN" http://<HA_HOST>:8123/api/config | head -c 200
```

`/api/states` 一次拉全部实体;`/api/services` 拉可调用的服务。

## 最小 Python 客户端

```python
import urllib.request, json
TOKEN = <从 .env 读 HASS_TOKEN>
def api(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("http://<HA_HOST>:8123"+path, data=data,
        headers={"Authorization":"Bearer "+TOKEN, "Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(req, timeout=20))
```

## 写入后必须回读验证

服务调用返回 `200`/`[]` **只说明 HA 接受了请求**,不等于有可观察效果。

- ❌ 别拿 `persistent_notification.create` 的 200 当证据:该通知**不落成 state 实体**,
  `/api/states` 里查不到(2026.9.2 实测,568 实体前后不变)。
- ✅ 回读用 **WebSocket** `persistent_notification/get`(本机 `websockets` 库可用):

```python
ws://<HA_HOST>:8123/api/websocket
# 收 auth_required → 发 {"type":"auth","access_token":TOKEN} → 收 auth_ok
# 发 {"id":1,"type":"persistent_notification/get"} → 返回列表
```

- 控制类实体改状态后,回读 `/api/states/<entity_id>` 核对 `state` + `last_changed`。
- 动用户真实设备(灯/窗帘/空调)前先问 —— 读接口随便用。

## 家底快照(2026-09-13 实测)

- HA 2026.9.2,站点名「我的家」,时区 Asia/Shanghai,**568 实体 / 62 服务域 / 271 服务**
- light 46 / switch 103 / cover 4(客厅+卧室米家窗帘)/ climate 3 / camera 3(含 CW300 户外)
  / media_player 7(小米家庭屏×2、8 寸屏、中控屏)/ automation + scene + script 可触发
- 手机推送:`notify.mobile_app_pixel_8`、`mobile_app_oppo_find_n5`、`mobile_app_oppo_n6`
  → **HA 能直接往用户手机推通知**(设备侧通道,可与微信/telegram 互为保险)
- 组件已装:`xiaomi_miot`(米家全家桶)、`hassio`(Supervisor)、`mobile_app`、`notify`
- 状态快照会变,数字只用来说明量级;每次要真实数字就现拉 `/api/states` 数。

## 401 会产生一条 HA 通知

未带 token 探测 `/api/` 会在 HA 里留一条 `Login attempt failed` 通知(来源=本机主机名 YFWL-Ian.lan)。
看到别慌 —— 多半是 agent 自己探活留下的,可顺手 dismiss。

## Hermes 侧接入(需重启 gateway + 启用插件)

插件 `plugins/platforms/homeassistant` 是**bundled 但默认不启用**的 —— 只重启 gateway 没用:

```bash
hermes plugins enable homeassistant-platform --no-allow-tool-override   # 先启用(提示 Takes effect on next session)
hermes plugins show homeassistant-platform                              # Status 应变 enabled
hermes gateway restart                                                   # 再重启
hermes gateway status                                                    # 看新 PID
```

- **重启 gateway 不会断开 desktop 会话**:desktop 的 chat 后端是另一个进程(`hermes_cli.main serve --host 127.0.0.1 --port 0`),
  gateway 是 Windows 计划任务 `Hermes_Gateway`。用 `Get-CimInstance Win32_Process` 分清两边再动手。
- 成功判据(`logs/gateway.log`):`Connecting to homeassistant...` → `[Homeassistant] Connected to http://…:8123`
  → `✓ homeassistant connected` / `Gateway running with N platform(s)`。
- ⚠️ **事件转发默认是关的**:没配 `watch_domains` / `watch_entities` / `watch_all` 时日志会报
  `All state_changed events will be dropped` —— 连上是连上,但什么都不转发。配置写在 gateway HA 平台
  的 `extra`: `{url, watch_domains[], watch_entities[], ignore_entities[], watch_all, cooldown_seconds(默认30)}`。
- **出站两条路不同**:在线 adapter 的 `send()` 用 `persistent_notification.create`(标题固定 "Hermes Agent",实测可用);
  **离线/cron 投递**(standalone sender)走 legacy `notify.notify` + `target=<chat_id>` ——
  2026.9.2 实测非设备 target(`notify` / `persistent_notification` / 编造名)全部 **HTTP 500**,
  只有 `mobile_app_<device>` 这类设备 target 才有戏;要在 cron 里推 HA 通知先实测确认。

## 改 HA 配置文件：匿名 SMB 直通(2026-09-13 实测)

**HA 的 `/config` 目录可以通过 SMB 直接读写,Samba 插件未设密码(guest 可写)**:

```bash
ls //<HA_HOST>/config          # 直接能列目录,无需凭据
cp file //<HA_HOST>/config/www/ # 直接能写
```

- 端口 **445 开着**就是入口;22222(SSH 插件)/1337(Code Server)/8099(File Editor) 都关着。
- ⚠️ `net view` 会报 1702,别被误导——直接访问 UNC 路径就行。
- **改任何文件前先建时间戳备份目录**(如 `/config/.hermes-backup-YYYYMMDD/`)再 cp 原件。

### YAML 模式仪表盘三个坑(都踩过)

1. **`!include` 的路径基准是仪表盘文件所在目录**,不是 /config:`dashboards/caiping.yaml` 里写
   `!include button_card_templates.yaml` → `Unable to read file /config/dashboards/...`;
   写 `!include ../button_card_templates.yaml` 才对。
2. **button-card 模板只从仪表盘配置里读**(`button_card_templates:` 写在 configuration.yaml
   顶层是无效的,前端永远看不到)→ 必须把 include 放进仪表盘 yaml 顶层。
3. **YAML 仪表盘是每次请求重新读盘的**——改完文件立刻生效,**不需要重启 HA**;
   验证方式:`ws → {"type":"lovelace/config","url_path":"<path>"}`,success=true 且能数出
   `button_card_templates` 数量就说明 HA 真的解析到了。

```python
# 读取/验证 YAML 仪表盘(WS)
{"id":1,"type":"lovelace/config","url_path":"caiping-ui"}
# 失败时 error.message 会带上具体行号与原因(如 Unable to read file …)
```

### 其他实测坑

- **scenes.yaml / scripts.yaml 可热加载**:写完 `POST /api/services/scene/reload` 立即生效。
- **中文场景名会被转成拼音式 entity_id**:`name: 离家` → **`scene.chi_jia`**(不是 li_jia),
  `晚安`→`scene.wan_an`,`观影`→`scene.guan_ying`。用 `id:` 显式指定最稳;
  **写完一定要回读真实 entity_id 再写进仪表盘**。
- **`triggers_update` 里不能放 JS 模板**(button-card 只接受实体 id 或 `all`)——
  模板里写 `- '[[[ return variables.entity ]]]'` 虽然能加载但不会更新,统一改 `all`。
- **button-card 的 `custom_fields` 必须配 `styles.grid` 区域**,否则多个自定义字段会叠在
  同一格里(模板里只有 styles.card 是残缺的)。
- **坐标要从底图的真实几何算**:floorplan.svg 的 `viewBox="0 0 1200 850"`,
  `left% = x/12`、`top% = y/8.5`;房间矩形直接从 svg 的 `<rect>` 里读,别凭感觉摆。
- **手机端常用 `floorplan.png`**`:svg→png` 用
  `chrome --headless=new --force-device-scale-factor=2 --window-size=1200,850 --screenshot=floorplan.png file:///…/floorplan.svg`,
  产物 2400x1700,丢进 `www/` 即可。

## 彩平图本地拖拽编辑器(2026-09-13 做好,本机常备)

HA 官方**不支持拖拽摆按钮** —— YAML 模式仪表盘没有 UI 编辑器;picture-elements 的编辑器
(仅 storage 模式有)也只是数字输入框,官方社区至今还在求拖拽。所以自建了一个:

- **位置**:`~/ha-caiping-editor/`(`server.py` + `index.html`),双击同目录
  `启动拖拽编辑器.bat`,`http://127.0.0.1:8765/`
- **原理**:起本地 HTTP 服务 → 读 `//<HA_HOST>/config/dashboards/caiping.yaml` 解析出
  带 `left/top` 的 button-card 元素 → 页面拖动图钉 → POST 回服务端 → 只改那两行数字
  (注释/模板/实体原样保留)+ 先备份 → 写回 SMB
- **效果验证**:YAML 仪表盘每次请求重读盘 → 存完刷新 HA 页面即生效

### 写这类本地小工具的两个教训(都真踩过)

1. **接口参数形状必须显式兼容**:前端发的是 `{left, top}` 对象,后端却按 `[0]/[1]` 取 →
   `KeyError: 0`;**报错又被 `str(ex)` 吐成一个裸 `0`**,界面上就只是“没反应/看不懂”。
   凡是自家前后端约定的字段,两边都写清楚,后端 `isinstance(v, dict)` 兼容两种形状。
2. **“没反应”往往是因为按钮被禁用**:无改动时 `disabled=true` 的保存按钮点下去毫无反馈,
   用户根本分不清“没改动”和“坏了”。→ 按钮常亮 + 无改动时明说原因;有改动时把数量写在
   按钮上(`保存到 HA (3)`);离开页面前提醒;服务端每次写盘打一行日志。

### 标签从哪来(元素定位靠注释)

解析器按 **`name:` > 紧跟元素上方的 `#` 注释 > 实体 friendly_name > 实体 id** 取名;
`# ---- 客厅（svg x...）----` 这类装饰分隔行要跳过,否则会变成标签。
温湿度卡这类没有 `entity:` 的元素(用 `temp_entity`/`humi_entity`)要回退到子实体,
否则右边列表里会显示“—”,用户就看不出这是哪个设备。

### 视图密度:手机端故意比平板端少

平板端 panel 全屏(图宽 >1000px)可站 22 个图钉;**手机端图只有 ~380px 宽,22 个 44px 按钮
会互相压住点不中**,所以手机端图上只放最常用的 8 个,其余全部走下方「设备控制」实体列表
(总共可操作反而更多)。这是用户认可的设计,不要“好心补齐”。

## button-card 模板两个致命坑(2026-09-13 实战: 卡片显示 error)

### 坑1: `[[[ ]]]` 不能套娃

```yaml
# ❌ 错——button-card 从第一个 [[[ 取到下一个 ]]],得到 var state = states[' → SyntaxError → 卡片显示 error
name: |
  [[[
    var state = states['[[[ return variables.entity ]]]'].state;
  ]]]

# ✅ 对——在 JS 里直接用变量，不要用模板插值
name: |
  [[[
    var e = states[variables.entity] || {};
    return (e.attributes.temperature || '--') + '°C';
  ]]]
```

**`variables.X` / `states` / `entity` 在模板里本来就能直接用,不需要再嵌一层模板去取。**
自查一行:
```python
import re
blocks = re.findall(r"\[\[\[(.*?)\]\]\]", open(f, encoding='utf-8').read(), re.S)
assert not [b for b in blocks if "[[[" in b]   # 应为空
```

### 坑2: `custom_fields` 里的嵌套卡,自己的字段要多包一层方括号

官方文档(advanced/js-templates):嵌套的 `custom:button-card` 里的模板要 **多一对 `[]`**:

```yaml
custom_fields:
  info:
    card:
      type: custom:button-card
      entity: '[[[ return variables.entity ]]]'   # 3 括号 = 父卡求值(父卡有 variables)
      name: |
        [[[[                                       # 4 括号 = 嵌套卡自己求值,可用自己的 entity
          var a = entity.attributes || {};
          return (a.temperature != null ? a.temperature : '--') + '°C';
        ]]]]
```

判断依据:**这个字段属于父卡还是嵌套卡**。父卡的 `variables` 在嵌套卡里也能读到(官方例子里
父卡 `variables.b` + 子卡 `variables.c` 同时可用)。

### 坑3: HA 会缓存 dashboard 的 `!include` 文件(最坑)

**只改 `button_card_templates.yaml` → WS 拿到的还是旧内容,而且不报错、不提示**(实测
连续两次请求都返回旧模板)。

```python
# 让 HA 重读 include 的办法:改一下【仪表盘文件】本身(哪怕只改一行的注释)
# 把 dashboards/caiping.yaml 的某行注释改掉 → 整个仪表盘(含 include)重新从盘上读 → 立即生效
```

- 结论:**改模板库后必须同时动一下仪表盘文件**(写一行注释/touch 内容),否则白改。
- 验证方法:`ws {"type":"lovelace/config","url_path":"..."}` 把返回的模板内容打出来跟盘上文件比对,
  别只凭“文件写了”就宣布修好。
- 不存在 second copy 的干扰:确认过 `/config/button_card_templates.yaml` 只有一份。

## picture-elements 卡片被压成一条 25px 白条(2026-09-13 实战,真凶)

症状:仪表盘上那张胶片卡只剩"上面一条"细白条，图标全挤成一条。

**根因:`aspect_ratio: "16/9"` 被 HA 当成数字 16** —— 卡片高度 = 宽度 / 16。
实测证据:卡片渲染 401×25 px，401/16=25，比例正好 16.04。这个坑从原作者那版就存在。

- ✅ 修法:**删掉 `aspect_ratio`,让图片用自身比例**(1024×576 的图自然就是 16:9)
- ❌ 不要写 `"16/9"` 这种字符串;要写就写小数(如 `1.7778`)
- **量卡片真实尺寸的方法**(不必登 HA):`computer_use` 抓那个浏览器窗口的截图 ——
  用 numpy 找亮度>120 的连通区域，算出卡片盒子的宽高比。

### 顺带:全屏(panel)与对齐

- `panel: true` + **有** aspect_ratio → 容器被拉成屏高、图保持比例 → 图只占上面一条、
  而且图标按容器高度百分比定位 → 全飘出图外("图全是错的")
- `panel: true` + **无** aspect_ratio → 容器≈图比例(实测 1210×665 vs 底图 1.78/满屏 1.82，差 2%)，
  **满屏且对齐** ✅ —— 这个组合才是全屏正解
- `max_columns: 1` / `column_width: 2000` 在 masonry 视图里**没用**(实测卡片仍 407px 宽，不会撑满);
  要撑满就用 panel
- 竖屏设备用 panel 会把图横向拉伸(图 1.78 vs 竖屏内容 ~0.7) → 竖屏需求要另做竖版裁图

### 改 HA 存储模式仪表盘的要点

- 读/写都走 WS:`{"type":"lovelace/config"}` / `{"type":"lovelace/config/save","config":…}`
  (非默认面板加 `url_path`);新建面板用 `{"type":"lovelace/dashboards/create",...}`
- 保存后前端**实时刷新**(无需重启/手动刷新);但**视图层配置(panel/列宽)变更需要重新加载页面**才看到
- 改前先备份整份 config 为 JSON(`lovelace.<名>.<时间>.json`)—— 存储模式没有 git 历史
- ⚠️ 同一张卡如果同时存在于两个面板(storage 是各存一份 JSON),改一处必须两处都改

## 相关

- HA 备份加密密码 / HAOS 换盘迁移 → skill `unraid-server-ops`(references/haos-vm-migration.md)
  ⚠️ 该文档 2026-08-13 写的「无 HA token」已过期,2026-09-13 起有令牌。
