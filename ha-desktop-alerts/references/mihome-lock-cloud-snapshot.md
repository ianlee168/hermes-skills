# 米家门锁摄像头的"云端抓拍"取图（2026-09-13 实测打通）

场景：小米智能门锁 4 Pro（`xiaomi.lock.s1`，门外摄像头 + 门内猫眼屏）没有在 HA 里被映射成
camera 实体，但**画面能从米家云取到** —— 用于"有人按门铃 → 电脑弹门口照片"。

## 结论（已验证）
按门铃那一帧的照片确实在米家云上，接口能给出来。`xiaomi.lock.s1` 的 miot 规格里有：
- `siid=7 eiid=1006` = Doorbell Ring（有人按门铃）
- `siid=17` = DoorLockCamera：`eiid=2 Someone At The Door` / `eiid=4 Someone Passed By`
- `siid=21` = WiFi-doorbell：`eiid=1 Doorbell Ring`

## 三步

### 1) 拿云事件（含门铃那一帧）
```
GET https://business.smartcamera.api.io.mi.com/common/app/get/eventlist
    did=<门锁did>&model=xiaomi.lock.s1&doorBell=true&eventType=Default
    &needMerge=true&sortType=DESC&region=CN&language=zh_CN
    &beginTime=<ms>&endTime=<ms>&limit=5
返回 data.thirdPartPlayUnits[]，每条：
  createTime / eventType(如 "Bell:Stay:FaceUnlock") / fileId / videoStoreId
  eventTypeDetail[] = [{event:"Bell"|"Stay"|"FaceUnlock"|"PeriodicPasswordUnlock", imgStoreId:"CAMERA_IMG_..."}]
```
- 走 HA 的 `xiaomi_miot/request_xiaomi_api` 服务就能调（`entity_id` 用门锁的任意实体、`crypt=true`），
  不用自己实现标准签名。
- **要挑 `event == "Bell"` 的那条 detail**，它才是按门铃那一刻的帧；退而求其次用最新一条有图的。

### 2) 用 rc4 签名换图片 URL
```
GET https://processor.smartcamera.api.io.mi.com/miot/camera/app/v1/img
    data={"did","fileId","stoId":<imgStoreId>,"segmentIv":<16 随机字节的 base64>}
```
签名（抄 `xiaomi_miot/core/xiaomi_cloud.py` 的 `rc4_params`，可直接用 `micloud` 库实现）：
```python
from micloud import miutils
nonce = miutils.gen_nonce()
sn = miutils.signed_nonce(ssecurity, nonce)          # ssecurity 来自云鉴权缓存
p['rc4_hash__'] = sha1_sign('GET', url, p, sn)       # sha1("GET&/path&k=v...&signed_nonce") 的 base64
p = {k: miutils.encrypt_rc4(sn, v) for k, v in p.items()}
p['signature'] = sha1_sign('GET', url, p, sn)
p['ssecurity'] = ssecurity; p['_nonce'] = nonce
url = api + '?' + urlencode(p) + '&yetAnotherServiceToken=' + service_token
```
- `sha1_sign`：路径取 url 的 path（`/app/` 前缀要去掉），`&`.join([METHOD, path, *"k=v", nonce]) 再 sha1+base64。

### 3) 解密：返回的是 **AES-CBC 加密的 JPEG**
```python
from Crypto.Cipher import AES
key = base64.b64decode(ssecurity)      # 16 字节
plain = AES.new(key, AES.MODE_CBC, segmentIv_bytes).decrypt(raw)   # 前两字节应为 ÿØ
```
（集成里是把 URL 交给 ffmpeg，用 `-decryption_key <ssecurity hex> -decryption_iv <segmentIv hex>` 解开，
所以手工取图必须自己 AES 解。）

## 云鉴权从哪来
`/config/.storage/xiaomi_miot/auth-<uid>-cn.json`（sid=xiaomiio）与 `auth-<uid>-cn-micoapi.json`
（sid=micoapi）里各有一套 `ssecurity` / `service_token`。**图片接口用 xiaomiio 那份能通**
（实测 micoapi 那份 401）。文件名是 ASCII，Windows 侧可直接读（同目录里 `urn:miot-spec-*` 那种含
`:` 的缓存文件名在 Windows 上打不开）。

## 坑
- 事件上云有延迟：按铃后约 5~15 秒才查得到 `Bell` 帧 → 监听程序里要**重试轮询**（每 3 秒，最多 ~30 秒），
  并且**先弹文字、图到了再弹一次带图的**（同一窗口替换 + Toast 用同一 Tag 覆盖，避免堆一屏）。
- 云事件的时间戳用于过滤：`ctime`（消息实体的属性）= 事件时间，用它当 `beginTime` 的下界，
  避免拿到上一次门铃的旧图。
- 同一把锁短时间重复按门铃，云消息可能不推（实测第二次没进消息实体）→ 触发源要有兜底。
