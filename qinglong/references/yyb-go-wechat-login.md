# YYB-Go(微信登录服务)部署 + 阿维塔/捷停车签到(2026-08-31)

## 背景
用户下载的"分享版"微信小程序每日签到脚本(阿维塔 avatr_分享版、捷停车 jesting_分享版)都走 YYB-Go 微信登录换凭证。Unraid 24/7 + 已有青龙面板 → YYB-Go Docker + 青龙定时任务。**这是用户的固定工作流:以后还会带更多分享版文件夹来,按本文件流程走。**

## YYB-Go-Enhanced 部署(全部实测通过)
1. 建网络:`docker network create qinglong_default`(YYB-Go compose 用 external 网络 qinglong_default;本机青龙在默认 bridge,不在这个网里)
2. `git clone https://github.com/525815266/YYB-Go-Enhanced.git /mnt/user/appdata/yyb-go`
3. 写 .env(参考 .env.example):`YYB_AUTH_DRIVER=sqlite`、`YYB_ADMIN_USER/YYB_ADMIN_PASSWORD`(预建管理员)、`YYB_BIND_ADDRESS=0.0.0.0`、`YYB_PORT=8000`、`PANEL_TYPE=qinglong`、`QL_URL=http://qinglong:5700`
4. `cd /mnt/user/appdata/yyb-go && docker compose up -d --build`(Go 编译 3-8 分钟;Dockerfile 内置 GOPROXY=goproxy.cn 国内代理;单容器、端口 8000、数据卷 ./data/{db,avatars,qr})
5. ⚠️ 权限坑:容器 yyb 用户(uid 100:101)写不进 root 属主的 ./data → `chown -R 100:101 /mnt/user/appdata/yyb-go/data` 后 restart
6. 浏览器 http://192.168.50.1:8000 → 登录 → 手机微信扫码添加账号 → 记 OpenID(状态 alive;约 25-30 天需重扫,服务端自动保活续期)

### YYB-Go API(管理/脚本共用)
- 登录(Web 会话):`POST /login` JSON {username,password} → 存 cookie jar
- 账号列表:`GET /accounts`(带 cookie);删除账号:`DELETE /accounts?ref=<openid>`(**不是 ?id=**,400 报 "ref query param is required")
- 脚本取微信 code:`POST /wxapp/getCode` body `{"ref": openid, "app_id": "<小程序appid>"}` → `data.result.code`(响应含 account 信息,可顺带核对绑定的是哪个微信)
- 多账号:每微信一个 openid;脚本配置按 `host:port/openid` 形式(脚本自动补 http://,127./192.168. 前缀按 http 处理)

## 阿维塔签到(avatr_sign.py,青龙任务 2283,`28 0 * * *`)
1. `POST {yyb_server}/wxapp/getCode`(appid `wx897fdd60b4bfbade`)→ code
2. `POST appserver-view.avatr.com/api/auth/thirdLogin`(MINI_PROGRAM 身份头)→ loginToken
3. `POST m.avatr.com/api/v6/signIn/signInRiskVerify`(AVATR_APP 身份头)→ 签到
- yyb_server 填 `http://192.168.50.1:8000`(容器内经宿主 IP 可达)
- README 强调:thirdLogin 用小程序头、签到用 App 头,appid 错报 1222
- **多账号(2026-09-15 查证)**: avatr_sign.py 只读**单个** `openid`(config.json 是字符串,不遍历数组)。加账号三前提:① 一个微信号=一个阿维塔账号 → 需另一个微信;② 该微信必须先在手机阿维塔 App 登录并签到激活过,否则 110000(同上面的坑);③ YYB-Go 扫码添加拿新 openid。落地二选一:改造脚本遍历 openids 数组(推荐,OPENID→列表 + main 循环)或复制脚本+config 到 `scripts/avatr2/` 建第二个任务(零改动、任务数变多)

### 风控 110000 的根因与解法(已闭环 ✅)
- 现象:管线 ①② 全通,③ 签到 `code=110000 风控监测到账号异常`;App/MINI 两种身份头都试过均 110000 → 与身份头无关
- **根因:扫码绑定的微信,其账号从未在手机 App 激活/签到过 → 风控见它陌生直接拦**(当时扫了"知猪侠"微信,非主力)
- **解法:YYB-Go 改绑「主力微信」**(重新扫码拿新 openid 写 config.json)→ 立即 ✅(返回 10402"今天已签到过"=防重复正常)
- 教训:部署这类签到先确认哪个微信绑的是真正在用的账号,别拿随便一台微信扫码

## 捷停车(jesting.py,青龙任务 2284,`0 9 * * *`)— 分享版脚本通用坑

1. **config.json 冲突(类级坑)**: 多个脚本都读同目录 config.json 会互踩(阿维塔已占 scripts/ 根)。**分享版脚本一律放子目录** `scripts/jesting/`(mv 脚本+config 进子目录),任务命令 `task jesting/jesting.py`;脚本用 `__file__` 定位 config,子目录隔离最稳
2. 依赖: `pip3 install 'httpx[http2]' httpx-socks pyjwt python-dotenv -i https://pypi.tuna.tsinghua.edu.cn/simple`(pycryptodome 阿维塔已装);脚本启动自检 jwt 库是否真是 pyjwt
3. 直测: `docker exec -w /ql/data/scripts/jesting qinglong python3 jesting.py`

### 静默失败调试法(类级技巧)
token 换到了但账号 0 成功、中间零输出 → 脚本某步 return 了但没 print。**写独立调试脚本直打原始响应**(getCode → token 接口原样 JSON + `jwt.decode(token, options={"verify_signature": False})` 打印 sub),一眼定位。

### 分享版脚本的两个实测 bug(新版接口漂移)
1. **JWT sub 字段漂移**: 捷停车新 token 的 sub 只有 `id`(serviceId)、没有 `userId` → parse_jwt 拿不到 user_id → run() 静默 return(判"JWT解析失败"但无输出)。补丁: `self.user_id = sub_data.get("userId") or sub_data.get("id")`。签到/任务接口实测认 serviceId。
2. **None 崩溃**: 账号未绑手机号 → `format_phone(None)` 的 `len(phone)` 炸(`object of type 'NoneType' has no len()`)。补丁: `if phone and len(phone) == 11:`。
- 改前 `cp jesting.py jesting.py.bak-20260831`;补丁后 grep 确认生效;同步本地副本
- PushPlus 推送可选(config plusplus_token)

## 环境事实
- Unraid 宿主无 python3、无 nerdtools → 一切 Python 走容器;docker compose v2.40.3
- 青龙容器内部端口 5700,宿主映射 6700;跨容器按名解析需 `docker network connect qinglong_default qinglong`
- 青龙脚本目录宿主机路径 = `/mnt/user/appdata/qinglong/scripts`(bind `/mnt/user/appdata/qinglong` → `/ql/data`)
- 凭据:gbrain `credentials/yyb-go-avatr` + `credentials/qinglong`(用户铁律:密码存脑库不落 skill)

## 账号掉线识别+重扫(2026-10-03 实测闭环，阿维塔/捷停车同时挂就是这个)

症状: 阿维塔日志 `❌ 出错: 连不上 YYB-Go(http://…:8000)。HTTP Error 502: Bad Gateway`，捷停车 `## 完成 ✅` 但 `📊 成功: 0/1`(静默版)。
**那个 502 是 YYB 自己返回的、不是容器挂了** —— 容器 `/health` 200、`Up 3 weeks` 照旧。所以别先重启容器，先看账号。

判据三连(任一成立就先按重扫处理):
1. `POST /wxapp/getCode` body `{"ref":"<openid>","app_id":"wx897fdd60b4bfbade"}` → `{"code":502,"msg":"call failed: refresh account credentials: refresh failed: code=-109 msg=RC_PARAMS_INVALID"}`
2. 容器日志: `keepalive: account id=N refresh failed: code=-109 msg=RC_PARAMS_INVALID`
3. `GET /accounts`(需登录 cookie)里该账号 `status:"unknown"`、`rescan_recommended:true`
账号约 **25–30 天**需重扫(与容器 Up 时长差不多时就该怀疑)。

重扫流程(全程走 API，不必把密码贴聊天/让用户自己登录):
1. `POST /login {username,password}` 拿 cookie(凭据取自 gbrain `credentials/yyb-go-avatr`，条目格式 `- 管理员: user / pass`)
2. `POST /qr` body `{}` → `{"session_id":…,"image_url":"/qr/<sid>/image","status":"pending"}`（⚠️ 本版 `?as_base64=true` 不生效，直接取图端点）
3. `GET /qr/<sid>/image` → 二维码 JPEG，存盘后用 MEDIA: 发给用户，让他用**手机微信**扫(必须主力微信；非主力会踩 110000)
4. `GET /qr/<sid>/poll` → 扫完变 `{"status":"authorized","errcode":405}`
5. ⚠️ **最后必做 `POST /qr/<sid>/confirm`** —— 网页版自动做，走 API 不调这步就永远停在 authorized(实测白扫一张)；成功后该账号 `status:"alive"`、`rescan_recommended:false`
6. 重扫**同一个微信 → openid 不变** → `scripts/config.json`(avatr) 与 `scripts/jesting/config.json` **无需改**；换了微信才要同步新 openid
7. 验证: `docker exec -w /ql/data/scripts qinglong python3 avatr_sign.py` 与 `docker exec -w /ql/data/scripts/jesting qinglong python3 jesting.py` → 期望 `✅ 阿维塔签到成功` / `📊 成功: 1/1`
8. 误扫/用错微信的那张: `POST /qr/<sid>/cancel` 作废掉(否则事后被 confirm 会绑错号)

**不要为这类到期挂监测**(2026-10-03 陛下明确否决): 阿维塔 App 自己会提醒用户去签到, 用户从 app 知道后就来找 agent 重扫。agent 收到"阿维塔/捷停车挂了"的消息时, 直接按上面 1-8 步走(取二维码 MEDIA 发用户扫 → poll → **confirm** → 单跑验证), 全程不需用户登 YYB 后台或提供密码。
