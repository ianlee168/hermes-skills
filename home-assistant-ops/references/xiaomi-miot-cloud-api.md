# Mijia / Xiaomi cloud access through HA (`xiaomi_miot`)

Use when you need Mi-Home data that HA has no entity for (device inventory, device
settings, events like a lock's doorbell press), or when you must know what a device
*can* do before guessing.

Prereq: the HACS `xiaomi_miot` integration is configured with the user's Mi account.
Its cloud credentials are cached in `/config/.storage/xiaomi_miot/`
(`auth-<uid>-cn-micoapi.json` → `ssecurity`, `service_token`; `devices-<uid>-cn.json`) —
**credential material: never echo, never copy into a repo or chat.**

## 1. Call any Mi-cloud API through HA

```python
POST http://<HA>/api/services/xiaomi_miot/request_xiaomi_api?return_response=true
header: Authorization: Bearer <HA token>
body:   {"entity_id": "<entity belonging to that Mi account>",
         "api": "/home/device_list", "data": {...}, "method": "GET"|"POST"}
# response: {"service_response": {...}}   (plus changed_states)
```

Pitfalls that cost real time:
- **`?return_response=true` is mandatory.** Without it the HTTP call still returns 200 and
  the payload comes back as `[]` — indistinguishable from “this API has no data”.
- `entity_id` selects the cloud/account/device context. Use a *device* entity
  (e.g. `sensor.<lock>_door_state`). The message sensor belongs to the account, not a
  device: passing it makes `/miotspec/prop/get` return an empty result.
- One cloud call = one device family; results are not merged across accounts.

## 2. Enumerate every device in the Mi account

```
api=/home/device_list, method=GET, data={"getVirtualModel": true, "getHuamiDevices": 1}
→ result.list[] = {name, model, did, isOnline, token, parent_id, parent_model, virtualModel, ...}
```

- This is how you find devices the HA integration never created entities for
  (unsupported models, other rooms, a lone camera/doorbell).
- Empty `parent_id` / `virtualModel` ⇒ no hidden child devices (a doorbell paired to a
display would show as a child).
- Each entry carries the device's LAN `token` → treat the whole response as a secret.
- Cross-check reality: the account list is authoritative for “does the user even own X”.

## 3. Read / write individual miot properties

```
read : api=/miotspec/prop/get, data={"params":[{"did":"<did>","siid":N,"piid":N}, ...]}
write: api=/miotspec/prop/set, data={"params":[{"did":"<did>","siid":N,"piid":N,"value":V}]}
→ result[] = {siid, piid, value, code, updateTime}
```

- `code: 0` = ok. **`code: -704002000` = property not readable** (write-only or
  event-only, e.g. a doorbell/history string) → that value can never be polled; use the
  message feed (§5) instead.
- Keep batches small (≈5 params per call); larger batches come back empty.
- Read-only probing is free. **Ask the user before writing device settings** (changing a
  lock's / camera's alarms, volumes, recording windows is a behaviour change for them).

## 4. Know what a model can do before guessing

```
GET https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:<kind>:<id>:<vendor>-<model>:<ver>
```

- Build the urn from the HA entity/device attributes (`model`, e.g. `xiaomi.lock.s1`) plus
  the kind from the spec family; the version (1/2/3) matters — v3 of a lock exposes
  doorbell/camera services that v1 does not.
- Output lists every service with its properties (siid/piid), events (eiid) and actions.
  Look for the **events**: they tell you what the cloud will report and therefore what the
  message feed can trigger on.
- ❌ Do **not** try to read HA's local spec cache
  (`/config/.storage/xiaomi_miot/urn:miot-spec-*.json`): the colon in the filename makes it
  unopenable from Windows — `os.listdir` lists it, but `open()`, `Copy-Item`, the
  `\\?\UNC\` prefix and MSYS all fail. Fetch the online spec instead; it is the same data
  and much faster.

## 5. The Mi-cloud message feed = the event trigger source

Entity created by `xiaomi_miot`: `sensor.mi_<user_id>_message`. It polls the Mi-cloud
message queue and exposes the newest message plus attributes:

| attribute | meaning |
|---|---|
| `title` | human text, e.g. `<lock name>: 11:07 有人按门铃` |
| `content` | device name |
| `room_name` | room as named in Mi Home (e.g. 大门) |
| `device_id`, `model` | which device |
| `event` | `<siid>.<eiid>` of the miot event |
| `event_data` | event arguments (piid/value pairs) |
| `timestamp`, `ctime` | device-local and unix time |
| `prev_message` | the previous message (cheap way to see the immediately preceding event) |
| `entity_picture` | image URL **when the message type carries one** (camera alarms) |

Use it for events that never become entities: doorbell pressed, unlocked by finger /
from inside, camera motion/loitering alarms, appliance notifications.

Caveats — verify, don't assume:
- **Not 1:1 with reality.** The cloud coalesces repeated messages in a short window, and a
  single physical action only yields the messages the device chooses to push. A doorbell
  press may produce a message one time and nothing the next.
- **Device doorbell messages are usually text-only** (`entity_picture` empty). Do not
  promise a picture from this feed; plan a separate image source.
- Earlier read messages are not in this queue. For history use HA's own API:
  `GET /api/history/period/<iso-start>?filter_entity_id=sensor.mi_<uid>_message` — that is
  how you prove what did or did not arrive.
- Don't poll `/v2/message/v2/typelist` yourself as a history source: it only returns
  unread/new items and the integration's own polling consumes them.
- Whether a camera/lock pushes *image-bearing* alarms depends on its own settings — read
  them via §3 (e.g. loitering capture switch, recording window, motion sensitivity) before
  concluding a picture is impossible.

## 6. Add-on / store inventory (no 401)

`/api/hassio/*` over REST answers **401** even with a valid long-lived token. Use the
WebSocket instead:

```
{"id":1,"type":"supervisor/api","endpoint":"/store/addons","method":"get"}
  → result.addons[] {slug, name, installed, version}
{"type":"supervisor/api","endpoint":"/addons/<slug>/info","method":"get"}
  → state (started/stopped), boot, options
{"type":"supervisor/api","endpoint":"/supervisor/info","method":"get"}
```

Unknown endpoints return `{"code":"unknown_command"}`; wrong filter params return
`invalid_format` — both mean the path/params, not the permission. Also useful:
`config_entries/get` (which integrations are installed — e.g. MQTT present as an add-on but
**no** `mqtt` domain in `/api/services` means the integration was never added),
`config/entity_registry/list` (includes **disabled** entities, unlike `/api/states`),
`config/device_registry/list`, `config/auth/list` (`is_owner` / `system-admin`).
