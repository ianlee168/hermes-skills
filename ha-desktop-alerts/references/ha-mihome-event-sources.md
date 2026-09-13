# 米家/HA 侧的事件源细节

本文件只装"怎么从 HA/米家拿到事件与属性"的具体接口细节(常驻弹窗程序见 SKILL.md 与
skill `windows-strong-reminders`)。

## 1. 云端消息实体(米家事件的总入口)

`xiaomi_miot` 把米家云通知落成实体 `sensor.mi_<uid>_message`:

| 字段 | 例 |
|---|---|
| state | `小米智能门锁 4 Pro: 11:07 有人按门铃` |
| `room_name` | `大门` |
| `event` | `7.1006`(门铃) / `2.1020`(锁事件:指纹/人脸/门内开锁) |
| `device_id` / `model` | `1193867054` / `xiaomi.lock.s1` |
| `entity_picture` | 有图时是图片 URL(**门铃消息通常为空**) |
| `prev_message` / `timestamp` / `type` / `title` / `content` / `event_data` | 辅助信息 |

集成内部按 `v2/message/v2/typelist` 轮询云端未读消息,并可能带上 `img_url` 作为 entity_picture。

⚠️ **`typelist` 这类接口只返回"未读/新"消息**:自己手动调一次可能把队列消费掉,
不要用它来回放历史;要看历史用 `/api/history/period/<ts>?filter_entity_id=sensor.mi_<uid>_message`。

## 2. 调 "xiaomi_miot" 的服务

### 关键坑:要返回数据必须加 `?return_response=true`

```bash
POST /api/services/xiaomi_miot/request_xiaomi_api?return_response=true
Content-Type: application/json
{"entity_id":"<该云账号下的实体>","api":"/miotspec/prop/get",
 "data":{"params":[{"did":"<did>","siid":17,"piid":1}]},"method":"POST"}
```

- 不加 `return_response=true` → 响应体是空 `[]`,看上去"调用成功"其实什么都没拿到。
- `entity_id` 要给**属于该米家云账号的实体**;给消息传感器这类实体可能返回空。
- 一次别塞太多 `params`(按 5 个一组分批读)。
- `code: -704002000` = 该属性不可读(靠事件/动作上报的项,如门铃服务的"当前时间"、
  门锁历史的"门铃记录"),**不要指望轮询它**。
- 同族服务:`get_properties` / `set_property` / `set_miot_property` / `call_action` /
  `get_device_data` / `get_token` / `request_xiaomi_api`。

### 列出米家账号全部设备(判断设备到底在不在米家)

```json
api = "/home/device_list"
data = {"getVirtualModel": true, "getHuamiDevices": 1}
method = "GET"
```

返回 `result.list[]` 每项含 `name` / `model` / `did` / `isOnline`(还含 `token`,**别 echo、
别写进任何仓库**)。多个 `xiaomi_miot` 配置实例可能指向同一个账号 —— 对比 `did` 集合即可确认。

### 查型号的 miot 规格

`https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:lock:0000A038:xiaomi-s1:3`

返回 services → properties / events / actions,能直接看出某设备有没有门铃事件、摄像头服务。
⚠️ HA 本地缓存(`/config/.storage/xiaomi_miot/urn:miot-spec-...json`)文件名含 `:`,
**Windows 侧能 listdir 但打不开**(Win32 不允许路径分量含 `:`;`\\?\UNC\` 前缀与
PowerShell 通配拷贝都不行)→ 改用上面的网页/云接口。

## 3. Supervisor(加载项/商店):REST 会 401,走 WS

```python
{"type":"supervisor/api","endpoint":"/supervisor/info","method":"get"}          # 版本/架构
{"type":"supervisor/api","endpoint":"/store/addons","method":"get"}             # 商店+已装列表
{"type":"supervisor/api","endpoint":"/addons/core_mosquitto/info","method":"get"}  # 单个加载项
```

- REST `/api/hassio/*` 即使拿的是 owner 的长令牌也回 401 → 别在那条路上耗,直接用 WS。
- `/store/addons` **不要传 `filter`**(报 `invalid_format`);返回体顶层就是 `addons` 列表。
- 想确认某设备/服务是否已配:`config_entries/get`(WS)列出全部集成。

## 4. 门锁/猫眼类设备的现实

以米家门锁(`xiaomi.lock.s1`)为例,供同类设备参考:

- 门铃是独立服务:`doorbell` siid 7 → 事件 `7.1006`;另有 `WiFi-doorbell` 服务事件。
- 门外摄像头是 `door-lock-camera` 服务(siid 17),有"有人逗留/有人经过"事件与实时视频开关;
  **`xiaomi_miot` 不映射这个服务类型 → HA 里不会出现 camera 实体**,拿不到画面。
- 可读设置(用于判断抓拍是否开着):摄像头开关、夜视、侦测灵敏度、有人逗留抓拍、逗留时长、
  录像时间段、实时视频推流开关。这些**能读也能写**,所以要动之前先问用户。
- 想要的画面只能靠:另加一台已接入 HA 的摄像头 / 厂商官方集成 / 自实现厂商云看家快照接口。
