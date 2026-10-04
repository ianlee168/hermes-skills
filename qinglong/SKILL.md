---
name: qinglong
description: Manage QingLong (青龙) scheduled task panel — check status, list envs/crons, diagnose failures, manage tasks. Use when user asks about 青龙, scheduled tasks, sign-in bots, or cron failures.
tags: [docker, scheduling, qinglong]
---

# 青龙面板 (QingLong) 管理

青龙面板是一个定时任务管理平台，常用于签到、监控、自动化脚本。

## 协作约定(2026-10-03 用户定)

- **面板的写操作只归一条会话/实例**(当前: 110妹@50.110 主会话);其它会话(同机其它聊天窗口、161姐@50.161)**只读**。理由: 已有两次真实冲突——A 会话把 `status` 写成 0(=running) 想修"运行中"反而复现症状, B 会话同时按枚举改成 1/2;且双方反复手动触发 JD 任务(不在计划时间的 16:34/16:49/17:02/22:42 四次)直接把账号送进风控敏感窗口。
- 接手前先 `sqlite3 ... "select id,name,status,pid,isDisabled from Crontabs where pd IS NOT NULL"` + 看 `RunningInstances` 最近行, 判断有无别人正在改造; 发现别的会话在动 → **停手报告用户**, 不要并行改。
- 手动触发任何需要“拿账号去换凭证”的任务(jd_wskey/jd_wsck/签换类)先问用户——这类任务多跑几次就可能被风控误判并把 cookie 自动禁用。
- 单一写者声明已落在面板目录: 宿主机 `/mnt/user/appdata/qinglong/OWNER.md`(容器内 `/ql/data/OWNER.md`)。**动手前先读它**;owner 不是自己 → 只读诊断 + 把「要改什么/证据/回滚方案」报给用户。
- 定位“这是谁改的”: 先看产物 mtime → `session_search` 自己的会话(**同机其它聊天窗口也算“自己”**,别一口咬定是另一台机器的分身) → 再查另一台机的 cron/session 存储(cron 常驻看 `~/.hermes/cron/`)。别凭印象归因。

## 用户环境

- **URL**: `http://50.1:6700` 或 `http://192.168.50.1:6700`
- **GitHub**: https://github.com/whyour/qinglong
- **认证**: Bearer Token

## 常用 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/envs` | GET | 获取/管理环境变量（任务配置） |
| `/api/crons` | GET | 获取/管理定时任务 |
| `/api/crons` | POST | 建任务: body 是**单个对象** `{"name":..,"command":..,"schedule":..}` — **不能包数组**(包数组报 `"value" must be of type object`,与 `/api/envs` POST 要数组**相反**;多任务逐个 POST) |
| `/api/crons` | PUT/DELETE | 改/删任务(改要完整对象 id+name+command+schedule;删 body 是**字符串 id 数组** `["2365"]`,返回 200 即真删) |
| `/api/user/info` | GET | 用户信息 |
| `/api/login` | POST | 登录获取 token |
| `/api/run/<id>` | GET | ⚠️ 返回 SPA HTML 不是日志 — 日志直接读宿主机文件(见下) |
| `/api/crons/run` | PUT | 触发任务执行: body 是**数组** `[id]`(不是 `{"ids":[...]}`) |
| `/api/crons/disable` | PUT | 停用任务: body 数组 `["id1","id2"]`(与 run 同款);启用同理 `/api/crons/enable`。⚠️ **id 必须是字符串**：传数字数组(`[2362]`)会被校验判空 → **全库一起操作**,两个方向都踩过: `disable` 把 63 个任务全停用；`enable` 把 55 个 JD 任务连"已停用"的意图一起**静默打开**(当晚 19:21/19:38 就用失效 cookie 跑起来了)。**调 enable/disable 前先备份全量 id+isDisabled 清单,调完立即复核 `isDisabled`**,别只看返回 code 200 |
| `/api/envs/enable` | PUT | 启用环境变量: body 是**数组** `["id1","id2"]`(id 为字符串);禁用同理 `/api/envs/disable` |
| `/api/dependencies` | POST | 加依赖: body 是数组 `[{"type":1,"name":"requests"}]` — **type 必须数字**(0=node/1=python3/2=linux)、**name 必须字符串**,数组/数字 name 都报 400 |

### env 写入的形状(2026-10-02 在 2.22 上逐一试错确认)

| 操作 | 正确形状 | 报错对照 |
|------|---------|---------|
| 新建 env `POST /api/envs` | **数组包对象,且不能带 `status` 字段**: `[{"name":"X","value":"<值>","remarks":"说明"}]` | `{"name":..,"value":".."}` → `"value" must be an array`; 数组包对象带 `status` → `"[0].status" is not allowed` |
| 改 env `PUT /api/envs` | 单个对象 `{"id":..,"name":..,"value":".."}`(不能带 status、不能包数组) | |
| 启停 env `PUT /api/envs/enable|disable` | 数组,且 **id 用字符串** `["21","23"]` | 数字 id 同 crons — 慎用 |
| 触发任务 `PUT /api/crons/run` | 数组 `["2355"]` | |

写完后**必须复核两处**: `GET /api/envs` 看 status=0,以及 preload 文件出现 `export X=`(见下节)。

⚠️ **preload 里的值是**带引号**的**(`export X='<值>'`)——拿它去探测第三方登录态前先 `strip("'\"")`,否则会把好值判成未登录(实测: 带引号探测得 `smzdm_id:0`,去掉引号同一串立刻返回正常昵称)。判"env 有没有生效"要用**去引号后的值**去请求一次第三方接口。

## 快速诊断：为什么失败多

### 第一步：看仪表盘（最快）

用浏览器打开 `http://192.168.50.1:6700` 登录后看仪表盘数据：

| 指标 | 含义 | 参考线 |
|------|------|--------|
| 成功率 | 今日成功/今日执行 | >80% 正常，<50% 异常 |
| 今日成功/失败 | 绝对数字 | 失败>>成功说明大面积问题 |
| 平均耗时 | 单任务运行时间 | >300s 说明有超时任务 |
| 已禁用 | 被禁任务数 | 正常应接近0 |

### 第二步：浏览器登录获取 token

```bash
TOKEN=$(curl -s http://192.168.50.1:6700/api/user/login \
  -X POST -H 'Content-Type: application/json' \
  -d '{"username":"用户名","password":"密码"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['token'])")
```

### 第三步：API 批量查任务状态

```bash
curl -s http://192.168.50.1:6700/api/crons?search=&t=$(date +%s) \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

关注字段：
- `isDisabled` — 1=已禁用（不会执行）
- `pid` — null=未运行/已完成，非null=正在运行
- `last_execution_time` — 最后执行时间戳
- `last_running_time` — 最后运行耗时（秒）
- `status` — **运行态枚举,不是启停开关**: `0=运行中、1=空闲、2=已禁用、3=排队`(源码 `/ql/static/build/data/cron.js` 里 `CrontabStatus[0]="running" / [1]="idle" / [2]="disabled" / [3]="queued"`;面板「状态」列照它渲染,所以 `status=0` 的行永远显示「运行中」)。启停一律看 `isDisabled`

### 第四步：查看具体任务日志

```bash
# 查看 cron_id 的执行日志
curl -s http://192.168.50.1:6700/api/run/<cron_id> \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

或用浏览器：定时任务 → 点任务 → "日志" 链接。

### 常见失败原因速查

| 症状 | 可能原因 | 排查方向 |
|------|---------|---------|
| 成功率<20%，大量任务失败 | Cookie 过期/失效 | 检查 JD_COOKIE 的 `pt_key`/`pt_pin` |
| 某脚本平均耗时>200s | 脚本逻辑慢或有死锁 | 看该脚本的日志 |
| 某任务 "24小时未运行" | 调度时间未到或 cron 表达式错 | 核对 schedule 字段 |
| 所有任务都失败 | 环境变量缺失 | 检查 `api/envs` 是否有 pt_key |
| 依赖安装任务失败 | npm/pnpm 依赖未安装 | 检查 "依赖管理" 页面 |

### 读日志/脚本内容: 直接用 API,别去爬宿主机 (2026-10-02 实测)

`/api/run/<id>` 返回 SPA HTML,但**这两条能读到真实内容**(带 Bearer token):

| 需求 | 端点 |
|------|------|
| 日志正文 | `GET /api/logs/detail?file=<日志目录名>/<文件名>`(key 从 `GET /api/logs` 树里取,目录名形如 `6dylan6_jdpro_jd_wskey`) |
| 脚本正文 | `GET /api/scripts/detail?file=<相对路径>`(如 `notify.py`、`6dylan6_jdpro/jd_wskey.py`) |
| 写/覆盖脚本 | `POST /api/scripts` body `{"filename":..,"path":"./","content":..}`(已存在则用 `PUT /api/scripts` 同形状) |
| 跑代码/脚本(在容器内真正执行) | ⚠️ **`PUT /api/scripts/run` 是空响**:body `{"filename":"x.py","path":""}` 会返回 `{"code":200,"data":<pid>}`,但实测**时不会执行**(两个测试脚本都没落盘)→ 真要在容器里跑代码: 建一个临时 cron 任务,`command` 写任意 shell 命令(如 `python3 /ql/data/scripts/_fix.py`)、`schedule` 给个永不触发的占位(如 `5 5 29 2 *`),再 `PUT /api/crons/run ["<id>"]`,输出读任务日志 |

所以「看任务日志」= 先 `GET /api/logs` 找到目录 children 里最新的 `title`,再 detail 取正文 —— 不必 ssh 宿主机、不必 docker exec。
(`GET /api/scripts?path=/` 列根目录会 403 暂无权限;带 `?file=xxx` 反而能列出整棵树。)

### 日志判读铁律:看结尾行,别看中间

任务日志中间出现 `403 (Forbidden)`/`Response code 403`/`领取次数不足`/`火爆了跳出` **不代表故障** — 脚本在遍历子任务(签到/浏览/领奖),重复领取已领完的奖励被拒是正常流程,会继续跑下一个。唯一判据是**结尾行**:`## 完成 ✅` = 正常(中间有多少失败行都忽略);`## 失败 ❌(退出码 N)` = 真问题才查。扫日志先 `grep -E "完成 ✅|失败 ❌"` 定位结尾,再决定要不要看中间。

同一任务的日志时间戳早于 cookie 恢复时刻 = 风控期残留,别拿旧日志当现状(先 `ls -t` 确认最新一份再判读)。判读前先跑 `date` 确认真实当前日期——会话可能跨天,按记忆里的"今天"推理会把旧日志当现场故障。**三处对表**: 本机 `date` + 容器 `docker exec qinglong date` + 任一外部 HTTP `Date` 头(api.github.com / baidu)。面板日志文件名看起来"比今天还新"时,多半是**你的会话记忆过期**(机器关机跨了天),不是时钟错;判"冷却 24-48h 够没够"、"今天到底跑没跑"之前先做这一步。

**占位 schedule 的任务不会自动跑**: `29 2 29 2 *`(2月29日)这类"不存在日期"的 cron 是作者留的占位,日志只可能来自手动/全量 run——这类任务的报错不影响日常,用户翻到旧日志问起时按此解释,别当故障追。

### 京东(faker3)任务批量秒退/零账号诊断(2026-08-31 实测)

| 症状 | 根因 | 修复 |
|------|------|------|
| 任务 1-2s 秒退,日志尾 `MODULE_NOT_FOUND / Cannot find module 'qs'` | 容器重建后 npm 依赖没装(青龙依赖管理安装全失败,registry 不通) | 进容器补装:`docker exec qinglong sh -c 'cd /ql/data/scripts && pnpm add got tough-cookie crypto-js https-proxy-agent big-integer axios png-js dotenv jsdom qs request tunnel redis global-agent ws form-data --registry=https://registry.npmmirror.com'`(faker3 常用包全集;国内必须 npmmirror;canvas 原生包可后补) |
| 脚本能跑但「共0个京东账号Cookie」 | JD_COOKIE 环境变量被禁用(status=1) | `PUT /api/envs/enable` body=["id串"] 启用;验证 `GET /api/envs` 看 status=0 |
| CK检测日志账号「已失效」 | **先分层查原因**(多端登录互顶 / 风控标记 / 30天到期)——别默认是过期 | 用 jdpro CheckCK 同款接口验真伪:带 mobile UA + Referer 探 `me-api.jd.com/user_new/info/GetJDUserInfoUnion`,返回 `{"msg":"not login","retcode":"1001"}` = 真失效(passport 302 跳登录页可作旁证,`uc/loginService` 恒 200 不算探测);确认后浏览器 F12 抓 pt_key/pt_pin 重填(第三方扫码工具已全挂,别推荐)。⚠️ **`1001` 只在有「已知可用的对照」时才可信**: 同一批请求里把一条确认能用的 CK 用同款探针再打一遍 —— 若**它**也返回 `1001`(或端点整片 `403`),说明是**探针本身被挡**(本机 IP/UA 被京东拒),此时不能据此判定任何账号失效,更不要在汇报里写"账号死了";唯一地面真值是该仓库自己的 CK检测/资产统计任务日志 |
| API 列表一堆「运行中」但容器内无进程 | pid 残留(失败任务状态没清),并非真在跑 | `docker exec qinglong ps aux` 确认真实进程;依赖修好后状态自愈 |
| CK检测报 `connect ECONNREFUSED 127.0.0.1:5600` | 脚本写死旧端口,青龙容器内部是 5700 | 不影响检测主流程(退回普通检测逻辑),已知搁置 |

判断「cookie 是不是真到期 / 到底哪天抓的」(用户问"这么快就 30 天了吗")：别信 Envs 表 createdAt/updatedAt — createdAt 是最初建记录的时间,updatedAt 会被**每次禁用/启用操作覆盖**(CK 检测自动禁用也会写 updatedAt),都不是抓取时间(且本版 `/api/envs` 干脆不返回这两个字段 → **无法从面板判断用户最后一次贴凭证的时间**;想判断"用户是不是重新抓过"只能把当前值与上次存下的副本对比,或直接问用户,别猜、别编一个日期)。看该仓库 CheckCK 的日志目录(`/ql/data/log/<repo>_jd_CheckCK/`,只存最近几次运行)里最后一次「状态正常」的日志日期,按 30 天期推算即可解释。另:jdpro CK 检测默认**只禁用不自动启用**——需 env `CHECKCK_CKAUTOENABLE='true'` 才会自动启用新 cookie,否则到期后必须人工重抓填回再 enable,任务会一直停着等。

### cookie 失效原因分层(先定性,再决定要不要让用户重抓)

**"刚抓几天又失效"通常不是过期** —— 按此优先级排查,别一失效就让用户重抓:

1. **多端登录互顶(最常见)**: 青龙用着网页 cookie 期间,用户又在京东 App/网页登录,京东作废旧凭证。**必问用户**: 失效时间窗内有没有在别的设备登录过京东。根治=一处登录为准,或改用 App 抓的 wskey(见下节)。
2. **风控标记后续作废**: 前几天发生过 IP 漂移 / 全量并发 / 面部识别,账号处于观察期,新 cookie 也会被静默作废(表现:任务报错但 env 还是 status=0,直到下一次 CheckCK 才禁用)。
3. **30 天自然到期**: 只有失效时间窗对得上 ~30 天才成立。

**用任务日志夹出失效时间窗**: 挑一个每天固定跑的同一任务(如每日 08:38/13:38 的 jd_joypark_task),`ls -t /ql/data/log/<repo>_<任务名>/*.log` 对比相邻两份——最后一次有「领取奖励/成功」的与第一次报错的之间就是失效窗口;拿这个窗口去问用户当天在别的设备做过什么,比反复重抓有效。任务日志里的失效表现是 `账号XXX执行异常 TypeError: Cannot read properties of undefined (reading 'length')`(接口拿不到数据),与 CheckCK 的「已失效」文案不同,别认错。

**用户要"先全停"时**: `GET /api/crons` 存全量 JSON → `PUT /api/crons/disable` body=启用中的 id 数组(一次全停)→ cookie 变量同步 `PUT /api/envs/disable`。**存下来的那份 id JSON 就是恢复清单**(`PUT /api/crons/enable` 同一数组),要主动把恢复命令告诉用户,别让他担心停不回来。

更新 JD_COOKIE 的 API 形状:`PUT /api/envs` body 是**单个对象** `{"id":..,"name":..,"value":..}` — 不能带 status 字段、不能包数组(都报 400)。删除 env:`DELETE /api/envs` body 是数组 `["id1","id2"]`(与 disable 同款)。

**env 体检法(哪些变量能删)**: 逐个 grep 脚本目录确认引用,0 引用 + 宿主仓库已删/已停 = 死变量可删。常见死变量: faker3 晒单开关(isComment/isCommentPic)、smiek2121 的 gua_log_token/gua_cleancart_*(仓库2024已死,任务停用)、旧活动配置(JD_Lottery/JD_CITY_HELPSHARE/opencard_toShop/dapai/jd_dplh_* — dapai 里是 2024-05 大牌活动 ID,明显过期)。删除前先备份全量 env JSON(恢复=POST /api/envs 包数组)。2026-09-08 实测:15 个 env 清理到只剩 3 个 JD_COOKIE。

**config.sh 同样有死 export 区**: 文件尾部的“其他需要的变量”段堆积旧仓库 export(guaopencard_*/guaunknownTask_*/JD_TRY/JD_CITY_HELPSHARE/jd_shop_draw_ids 占位符等),删前逐个 `grep -rl <var> scripts/` 确认 0 引用。⚠️ 尾部 export 区里有**非死项必须保留**: `IPPORT='127.0.0.1:5700'`(.py 工具连 API 用,误删全挂)。顺带修: `PipMirror` 豆瓣源(pypi.doubanio.com)已停服多年 → 清华;`AutoStartBot` 没配 bot.json(占位符)就设 false 别自启。改完 `sh -n config.sh` 验语法。

**京东资产统计(jd_bean_change)报「0豆/0红包」= 大概率取数失败,不是真没豆**(2026-10-02 实测): 判据看日志里该账号段落 —— 出现 `Response code 403 (Forbidden)` / `401 (Unauthorized)` + `TotalBean API请求失败` 就是 cookie 已失效(脚本仍会打印一行「普通会员/0豆」的假报告);真·活账号的段落会多出【钱包余额】【新农场】【话费积分】等字段。收到这种日报先 `me-api` 探一次 cookie 再下结论。

**wskey 自动续期机制**(免每 30 天手动抓 pt_key): jdpro 的 jd_wskey.py / jd_wsck.py 任务读 env `JD_WSCK`(多账号用 `&` 连接),通过 appjmp 接口换新 pt_key 并**自动 PUT 回 JD_COOKIE + enable** — wskey 有效期远长于 pt_key(数月 vs 30天),抓一次自动续命。诊断: 任务日志出现「未添加JD_WSCK变量」= env 压根没建(任务本身正常);确认 5700 端口检查通过(IPPORT 已配)后,只需用户手机抓 wskey 填入。抓 wskey 也是账号授权操作,有风控风险 — cookie 刚被风控/触发过验证时缓几天再弄。

**排查“cookies 怎么突然就失效了”之前先看任务到底有没有在跑**: `GET /api/crons` 把每个任务的 `last_execution_time` 按日期统计一下 —— 实测 2026-10-02 当天: 63 个任务里 50 个 last_run 停在 09-08~09-11,只有 12 个是当天跑的。也就是说那三周里 JD 任务根本没执行、没人检查过 cookie,“坚持了多久”从未被现实验证;用户问“不是能撑半个月吗”时,先把这段停摆史摆出来再谈寿命。

## 部署新脚本到青龙(2026-08-31 实测,免 API 鉴权的文件直投法)

青龙容器 bind mount:宿主机 `/mnt/user/appdata/qinglong` → 容器 `/ql/data`(查 `docker inspect qinglong` 确认)。因此**不用 API 也能部署**:

1. 脚本直接 scp 到宿主机 `/mnt/user/appdata/qinglong/scripts/`(任务命令 `task <script>.py`,相对 scripts 目录)
2. 依赖用 `docker exec qinglong pip3 install <pkg> -i https://pypi.tuna.tsinghua.edu.cn/simple`(装进容器 python 环境,持久)
3. 直测:`docker exec -w /ql/data/scripts qinglong python3 <script>.py`(⚠️ 默认 workdir 是 /ql,不 -w 会 "No such file")
4. 日志文件在宿主机 `/mnt/user/appdata/qinglong/log/<任务名>/<时间戳>.log`(API 的 /api/run/<id> 返回 SPA HTML 没用;触发运行后 find -mmin -N 找新日志)
5. 跨容器 DNS:青龙默认在 docker 默认 bridge(非 qinglong_default),要让它被别的容器按名解析(如 YYB-Go 的 QL_URL=http://qinglong:5700)需 `docker network connect qinglong_default qinglong`。青龙**容器内**端口 5700,宿主映射 6700
6. 青龙登录凭据在 gbrain `credentials/qinglong`(别到处问密码)
7. ⚠️ **多个脚本共用 config.json 会互踩**(阿维塔/捷停车都读同目录 config.json):分享版脚本一律各自放子目录,如 `scripts/jesting/`,任务命令 `task jesting/jesting.py`
8. ⚠️ **子目录脚本必须再放一份 `notify.py`**: 子目录里 `from notify import send` 会静默失败,日志头报 `⚠️ 未加载通知模块,跳过通知功能` — Python 的 sys.path[0] 是脚本所在目录,找不到 scripts 根的 notify.py。修复 `docker exec qinglong cp /ql/data/scripts/notify.py <子目录>/`(副本,青龙 notify 大更新时手动同步),复跑应显示 `✅ 已加载notify.py通知模块`
9. **第三方多平台签到脚本库**(先按用户实际有账号的平台筛选、只下载选中脚本、子目录隔离、依赖与 env 变量名自检、`POST /api/crons` 形状、随机延迟含义)→ 见 `references/third-party-signin-scripts.md`
8. **微信小程序签到分享版脚本**(依赖 YYB-Go)完整流程、YYB-Go 部署、风控/接口漂移等坑 → 见 `references/yyb-go-wechat-login.md`

## 第三方签到脚本库(qlhub 类)部署要点 (2026-10-02 实测)

源: https://github.com/agluo/ql-script-hub(多平台签到: 夸克网盘/恩山/SMZDM/NodeSeek/顺丰/阿里云盘/百度网盘等,每个脚本要单独配环境变量)。

部署四坑(都踩过):
1. **子目录脚本找不到根目录的 notify.py**: 脚本放 `scripts/qlhub/` 时 `from notify import send` 失败(Python sys.path[0] 只含脚本目录,不像 node 会向上找 node_modules)→ 修复: `cp /ql/data/scripts/notify.py /ql/data/scripts/qlhub/`。验证日志出现 "✅ 已加载notify.py通知模块" 即修复。
2. **POST /api/crons 要单个对象**(不是数组!): `{"name":..,"command":..,"schedule":..}`;而 POST /api/envs 要**数组**——两者相反,报 "value must be of type object" / "[0].value is not allowed to be empty" 就是形状错了。中文任务名必须写 JSON 文件 --data-binary 提交。
3. **长 cookie 值必须走 JSON 文件**: 夸克 cookie 2KB+ 含 %;& 等字符,shell 拼接必炸;write_file 写 JSON → curl --data-binary @file。
4. **随机延迟干扰测试**: 脚本默认 `RANDOM_SIGNIN=true` + `MAX_RANDOM_DELAY=3600`(最多随机等 1 小时)。测试时临时建 `RANDOM_SIGNIN=false` 环境变量,验证后删除恢复。

依赖: 大多数脚本只需青龙内置;nodeseek 需 `pip3 install curl_cffi -i https://pypi.tuna.tsinghua.edu.cn/simple`。各脚本环境变量名见其 README(quark=QUARK_COOKIE、enshan=enshan_cookie、SMZDM=SMZDM_COOKIE、nodeseek=NODESEEK_COOKIE、顺丰=sfsyUrl 需抓包)。env 名以脚本自身 `os.getenv("...")` 为准,别照抄 README。

**顺丰 `sfsyUrl` 不是 cookie**,而是一条**分享/回跳 URL**: `mcs-mimp-web.sf-express.com/mcs-mimp/share/weChat/shareGiftReceiveRedirect?...` 或 `.../mcs-mimp/share/app/shareRedirect?...`(顺丰 App/小程序 → 我的 → 积分 → 分享/赠礼 生成, 链接里带登录凭证)。脚本拿它 GET 一次,从响应里取 `_login_user_id_`/`_login_mobile_` 两个 cookie 完成登录 —— 所以抓不到、不及时都会直接失败。多账号换行分隔,可加 `@UID_xxx` 备注,脚本自述要求 URL 编码;链接等同密码且有实效(几小时~几天)。用户嫌麻烦时可先停用该任务(否则每天到点报一次 `未获取到sfsyUrl`)。

### 从"全站 cookie 转储"里扒单个平台的 cookie (2026-10-02 实测)

用户常直接丢一整份浏览器 cookie 转储(几十万 token、**无域名划分**、上千个 cookie 名),按平台**特征名/前缀**定位,别指望有域名字段:

- **Discuz 论坛**(恩山/多数中文论坛): cookie 组形如 `xxxx_2132_*`(saltkey/auth/lastvisit/lastcheckfeed/lip/sid/...)。前缀是站点随机串 → 先取本站 cookiepre: `curl -s https://<站点>/ | grep -o "cookiepre[^,;]*"`(恩山 `www.right.com.cn` = `rHEX_2132_`),再从转储 `grep -o -E "<前缀>[A-Za-z0-9_]*=[^;]*"` 抽出整组拼成 cookie。
- **必须验证是真登录态**(光有 cookie 名不算): 带 cookie 请求一次看登录特征 —— Discuz 页面出现 `action=logout` 且 `discuz_uid = '<uid>'`(游客无此串);SMZDM 用 `curl -H "Cookie: ..." 'https://zhiyou.smzdm.com/user/info/jsonp_get_current'`,里 `"smzdm_id":0` = **未登录**(SMZDM 登录态靠 `sess`;转储里没有 `sess` 就是没登录,`_aUID`/`__ckguid` 只是跟踪 cookie)。NodeSeek 同理无会话 cookie 就配不了。
- 结论: 转储能救回"确实带登录态"的站(Discuz 系最典型);缺会话 cookie 的只能让用户在**已登录浏览器**里单独抓对应请求的 Cookie 头。
- ⚠️ **按特征名找会漏**: NodeSeek 的会话 cookie 叫 `session`+`smac`,名字毫无站点特征(之前的结论"NodeSeek 无会话 cookie"是错的)。找不到时改用下面「分批+二分」法。

### 未知名 cookie 的定位法: 整份 jar 分批 + 二分 (2026-10-02 实测,专治"转储无域名")

按站点特征名找不到会话 cookie 时:
1. 把转储解析成唯一 `name=value` 对,按 ~45 个一批,整批当 Cookie 头打给站点的**只读接口**(如 NodeSeek `GET /api/account/credit/page-1`),看响应从"未登录"变成真数据 → 服务端只认自己的名字,无关 cookie 无害。注意: 部分批会被 Cloudflare 拦(403 `Just a moment`),那是盾不是登录失败,多跑几次/避开即可。
2. 命中批次用**二分法**砍(每次砍一半,留仍返回真数据的半边)→ 收敛到最小集合。
3. 实测结果: **NodeSeek = `session=<40位>; smac=<ts>-<hash>`**(`pjwt` 那个 JWT 形态 cookie 实测不需要);带上即签到成功("今天的签到收益是5个鸡腿")。
4. 两份转储对比时注意: 同名不同值会自动刷新(session/`__cf_ob`/`cf_clearance` 等),取 smac 时间戳更大的那份即可。

### crond 真实链路的三个事实 (2026-10-02 实测, 2.22)

1. **env 下发链**: 面板 API 写 env → 面板重写 `/ql/shell/preload/env.sh`(每行 `export NAME=<值>`)→ 容器内 crond 触发 → `task`/`otask.sh` 里 `. $file_env` 注入 → 脚本读到。**直写 Envs 表不会触发 preload 重写**,任务照旧报 `❌ 未找到 X 环境变量`。自检命令: `grep -o 'export [A-Za-z_]*' /ql/shell/preload/env.sh`(该文件通常只有几行;写 `grep '^NAME='` 匹配不到 `export NAME=` 会误报缺失),顺带比 mtime 确认是刚刷的。
2. **启停的真字段是 `isDisabled`(0=启用/1=停用),`status` 不是开关**: 实测两者会不一致(NodeSeek `status=1` 但 `isDisabled=0` 仍在跑;任务跑完后面板会改写 `status`)——拿 `status` 判断启停会误判。查启停一律看 `/api/crons` 返回的 `isDisabled`。**停用在系统 crontab 里的落地方式 = 把该行注释掉**(`# 38 11 * * * … ID=2335`),所以 `crontab -l | grep -c <仓库名>` 会把已停用的行也数进去 → 判断"到底停没停"要数**不以 `#` 开头**的行,别只看总数。
3. **容器内 `task <脚本>` 不能用来验证 env**: 它不注入 env(与 crond 路径不同,`/proc/<pid>/environ` 可证)。要真验证就临时把计划改到 2 分钟后、观察日志头里 `共发现 N 个Cookie` / `❌ 未找到`,验完**立刻改回**原计划。
4. **上一轮实例没退干净 → 到点的下一次调度被跳过**: 随机延迟期间进程一直活着并占着 pid,面板判定「已在运行」就不再拉起(实测 18:09 启动的实例睡到 18:22,18:39 那次到点**无日志**)。排查: `ps -eo pid,etime,args | grep <脚本>` 看长时间挂着的实例;要做按计划的真实验证,先 kill 陈旧实例再清 pid(见「运行中」节),否则会误判成"调度没生效"。
5. **env 快照在进程启动那一刻**: `otask.sh` 启动时 `. $file_env`,而「未找到 X 环境变量」的打印在**随机延迟之后** —— env 是这一轮跑到一半才写进 preload 的,这轮仍会报缺失;别据此判定 env 没下发,核对 preload 里的值本身。

### 写 env 的另一条路: 直写 Envs 表(拿不到 API token 时)

老版本无 `Tokens` 表(登录态在 `Auths`),拿不到 bearer token 时直改库: python3 跑
⚠️ **直写库能改值/状态,但不会让面板重写 preload** → 任务读不到;写完必须再经 API 触发一次(如 `PUT /api/envs` 改 remarks、或 enable)把 preload 刷出来。
`INSERT INTO Envs (value,timestamp,status,position,name,remarks,createdAt,updatedAt,isPinned,labels) VALUES (?,?,1,0,?,?,datetime('now'),datetime('now'),0,'[]')`
— **status=1 才是启用**(禁用=0);同名已存在就 UPDATE,别插重(UNIQUE(value,name))。改完 `docker exec qinglong python3 /tmp/x.py` 复核 + `SELECT id,name,status,length(value) FROM Envs`。

验证"面板路径能读到新 env": `docker exec qinglong task qlhub/xxx.py` 触发一次真实运行(容器内 `task` 在 /usr/local/bin/task)。⚠️ 脚本的 env 检查发生在**随机延迟之后**(日志先出 `🎲 随机延迟: N分N秒`),面板跑一次可能等几十分钟才见结果,别当卡死;失败的样子是日志里 `❌ 未找到<var>环境变量`。日志落在宿主机 `/mnt/user/appdata/qinglong/log/<repo>_<脚本名>/<时间戳>.log`。

## faker3 京东脚本全灭排查 (2026-08-31 实战)

症状: 所有 shufflewzc_faker3_main 任务 1-2 秒秒退, 日志 `MODULE_NOT_FOUND` (如 Cannot find module 'qs'); 任务 pid 残留显示"运行中"但容器内无进程。

三层根因排查顺序:
1. **依赖缺失**: 容器重建后依赖安装全失败。修复: `docker exec qinglong sh -c 'cd /ql/data/scripts && pnpm add <包名...> --registry=https://registry.npmmirror.com'` (faker3 需 got tough-cookie crypto-js https-proxy-agent big-integer axios png-js dotenv jsdom qs request tunnel redis global-agent ws form-data; canvas 原生模块易失败可跳过)。验证: `cd /ql/data/scripts && node -e "require.resolve('got')"` (注意 cwd 必须是 scripts, 模块在 /ql/data/scripts/node_modules)。
2. **JD_COOKIE 被禁用**: `api/envs` 看 status=1。启用: `PUT /api/envs/enable` body `["id1","id2"]`。更新 cookie 值: `PUT /api/envs` body **单个对象** `{"id":1,"name":"JD_COOKIE","value":"pt_key=..;pt_pin=..;"}` (不能带 status 字段, 不能包数组)。
3. **Cookie 过期**: 跑 京东CK检测(1503) 确认; 过期需用户 F12 重抓 (https://www.jd.com → 应用→Cookie→pt_key/pt_pin, 30天有效期)。第三方扫码站大多已死, 别推荐。

其他坑: 脚本连青龙 API 默认 5600 端口(实际 5700), 检测脚本只能退化为普通逻辑; 脚本内 telegram 通知代理指向容器内不存在的 127.0.0.1:1081 导致通知失败 — 修复见「脚本通知(telegram)失败排查」节(不影响任务本身)。环境变量 api/envs POST 创建要包数组。

## faker3 → jdpro 迁移 (2026-08-31 实战)

faker3(shufflewzc/faker3) 更新变慢后, 社区主流转向 **6dylan6/jdpro**(4485★, 日更, 任务名 jd_*.js 与 faker3 兼容, 是事实继承者)。迁移要点:

- **订阅**(老版青龙无 /api/subscribes 路由, POST 报 `Cannot POST /api/subscribes`):新建走 UI → 订阅管理;存量订阅的停/删/改时间直改 sqlite Subscriptions 表(见「订阅管理」节),老版无 API 可调
  `ql repo https://js.googo.win/https://github.com/6dylan6/jdpro.git "jd_|jx_|jddj_" "backUp" "^jd[^_]|USER|JD|function|sendNotify|utils"` (国外机去掉加速前缀)
- **拉取很慢(几分钟)**: repo/scripts 目录会陆续出现, 别过早判定失败; 判断依据看 `log/<repo名>/` 的"添加成功"日志
- **订阅拉下来的任务在本环境默认启用** → 新旧仓库任务会双跑(同一活动跑两遍), 迁移必须停旧启新
- jdpro 自带 jd_indeps 依赖安装**经常全失败**(registry 问题, 日志一排 ❌ 失败), 但**非致命**: 共享 `/ql/data/scripts/node_modules` 已被 faker3 修复时装好, jdpro 脚本能解析(node 向上查找); 缺的补 `pnpm add date-fns moment cheerio ds --registry=https://registry.npmmirror.com`
- 停旧任务: `PUT /api/crons/disable` body 数组; 动手前先 `GET /api/crons` 存 JSON 备份(撤销=重新 enable)
- 验证迁移成功: 跑 jdpro 的 jd_CheckCK, 三账号"状态正常"即通
- faker3 独有任务 jdpro 无对应(资产统计/一键价保/删券/晒单/试用/路飞账密/github拉库修复等) — 清理前逐项核对:独有项几乎全是**过期限时活动**(大牌04xx~06xx、生肖金币等),仅少数通用项(试用/删券/查IP)有保留价值;列清单问用户再删,勿一刀切

## 订阅管理(2.22 有 API;更老版本才只能直改 sqlite)

**2.22 实测有完整 API**(2026-10-04):

| 操作 | 端点 | 形状 / 坑 |
|------|------|-----------|
| 列出订阅 | `GET /api/subscriptions` | 返回 `data[]`,字段 `url/schedule/whitelist/blacklist/log_path/autoAddCron/autoDelCron` |
| **立即拉取** | `PUT /api/subscriptions/run` | body 是**数组** `[7]` → 200;实测 14 秒跑完,日志写进该订阅自己的 `log_path` |
| 改订阅 | `PUT /api/subscriptions` | 单对象,但 **`autoAddCron`/`autoDelCron` 必须是布尔值**:库里存的是 1,原样 PUT 回必 400 `"autoAddCron" must be a boolean`(三种形状都试过)→ body 里改成 `true` 才过 |
| 直改库(兜底) | `Subscriptions` 表 | **改完不需要重启容器**:实测改 `url` 后下一次拉取立刻用新值(与老版「必须 docker restart」的结论相反) |

老版本青龙(没有 /api/subscribes 路由,请求回 SPA HTML / 404)仍只能直改数据库:

- 库:容器内 `/ql/data/db/database.sqlite`,表 `Subscriptions` — 字段是 snake_case:`is_disabled`(不是 isDisabled)、`schedule`、`schedule_type`='crontab'、`autoAddCron`/`autoDelCron`
- 停用/启用:`UPDATE Subscriptions SET is_disabled=1 WHERE id=N`(1=停,0=启)
- 改拉取时间:`UPDATE Subscriptions SET schedule='30 1,13 * * *' WHERE id=N`
- **改完必须 `docker restart qinglong` 才生效**(调度驻内存);重启前 `docker exec qinglong ps aux` 确认真进程 — API 里成片 pid 是残留假象,不是真在跑,可安全重启

### 跨 ssh+docker 跑 sqlite:引号地狱的标准姿势

一行 ssh 里嵌套 docker exec + sqlite3 + SQL 字符串字面量,引号必炸:SQLite 的 `"..."` 是**标识符**不是字符串,`schedule="30 1,13 * * *"` 报 `no such column`;heredoc 再包一层同样炸。可靠姿势:

1. write_file 写 .sql(SQL 字符串一律单引号)→ scp 宿主机 → `docker cp` 进容器
2. 容器内执行:`docker exec qinglong sh -c 'cat /tmp/x.sql | sqlite3 /ql/data/db/database.sqlite'`
3. **以 SELECT/changes() 的输出为验证,别信 `&& echo DONE`**:`docker exec ... < 宿主机文件` 的 stdin 重定向不可靠 — 曾 exit 0 + echo 假成功,实际一行没执行;必须随后 count 确认
4. **容器内 `sqlite3` 命令可能不存在**(`which sqlite3` 空,镜像未带或容器重建后丢)→ 换 python3 跑脚本文件,免引号地狱且稳定:write_file 写 .py(`import sqlite3; con=sqlite3.connect("/ql/data/db/database.sqlite"); cur=con.cursor()`)→ scp + `docker cp` 进容器 → `docker exec qinglong python3 /tmp/x.py`。写库后 `con.commit()`。
5. **改完值要核对没有多余空白**:SQL/bin 拼接时引号处理不当会把空格写进值(实测 schedule 变成 `' 30 1,13 * * *'` 前导空格)→ 打印 `repr(old)` / `repr(new)` 对比确认,别只看 `UPDATE` 返回成功。

### 拉库订阅的频率常识

- `27 8,12,16,20,0 * * *` = 每天 5 次(00:27/08:27/12:27/16:27/20:27),批量建订阅的常见默认,对拉库是浪费
- 订阅只刷新本地脚本,**任务执行时才读脚本** → 拉库频率只决定拿上游修复的滞后时间,≠ 任务执行频率
- 日更仓库 1-2 次/天足够(`30 1,13 * * *` 凌晨+午后),更新慢的 1 次/天;5 次/天徒耗 GitHub 匿名配额,易触发限流
- 订阅带 autoAddCron=1 时上游每加脚本自动建任务且**默认启用** → 已废弃仓库的订阅不删,上游一更新就和主力仓库双跑;更要紧的是**它会把用户手动停用的任务重新启用**(实测: 手动停用的 55 条任务在当日 01:30 拉库后又跑起来)。要"长效停用"必须三选一并在动手前告知取舍: 关该订阅的 `autoAddCron` / 把计划改成远期占位(如 `0 0 1 1 *`) / 停用订阅本身。
- **拉库日志是独立命名空间,别当成"账号任务跑过了"**: `GET /api/logs` 里 `<仓库名>/<时间戳>.log`(如 `6dylan6_jdpro/…`)是**订阅拉取任务自己**的日志。报 `fatal: could not read Username for 'https://<host>'` = 拉取源现在要账号密码(第三方加速域挂了/转私有)→ 脚本库**冻住**: 本地那份仍能照跑,但拿不到上游修复。先换源/修源再谈跑脚本;也别把这类日志当作今天 JD 任务执行过的证据。

### 6dylan6/jdpro 的公开上游已死 → 换 gitclone 镜像 (2026-10-04 实测)

- 上游 `github.com/6dylan6/jdpro` 现在直接 **401**(转私有/下架),所以一切以它为上游的加速域都报 `fatal: could not read Username for 'https://<host>': No such device or address`(git 想弹账号密码但无 TTY)。实测挂掉的一串: 原配置 `js.googo.win`、`ghproxy.net`、`gh-proxy.com`、`hub.gitmirror.com`;`ghfast.top` 另报 `remote: Please upgrade your git client.`
- **可用镜像**: `https://gitclone.com/github.com/6dylan6/jdpro.git` —— 容器内实测 14 秒克隆成功,HEAD `fa191ffb`(2026-09-17),71 项文件,`jd_wskey.py` md5 `4db416a28f` **与本地面包逐文件相同** → 换源不会降级;代价是内容冻结在 09-17(上游私有后不会有新修复)
- 换源步骤(可一键回滚,留好旧 URL): 改 `Subscriptions.url` → `PUT /api/subscriptions/run [<订阅id>]` → 读该订阅日志见「拉取 <alias> 成功...」+ `/ql/data/repo/<alias>` 目录出现 → 复核 `/ql/data/scripts/<alias>` 文件数/关键脚本 md5 未变
- **路径关系**: 拉取目标 `/ql/data/repo/<alias>` **只在成功拉取过之后才存在**(一直失败就一直缺);脚本真实运行目录是 `/ql/data/scripts/<alias>`;订阅 autoAddCron 建出来的任务行都带 `sub_id=<订阅id>`(查「这批任务是谁建的」看这个字段)

### 整仓库退役清理(遵守删除红线:先备份、可撤销)

1. 核对旧仓库任务全禁用(isDisabled=1),有启用中的先停
2. 全库备份:`sqlite3 db ".backup /ql/data/db/full_backup_<ts>.db"`
3. 一个 .sql 里删干净(用 cat|sqlite3 执行),再 `SELECT changes()` 看删除行数:`DELETE FROM Subscriptions WHERE id=<N>; DELETE FROM Crontabs WHERE command LIKE '%<仓库目录名>%';`
4. 脚本目录 mv 不 rm:`mv /ql/data/scripts/<repo_dir> /ql/data/.trash_<repo>_<ts>` — 删除红线:显式同意 + 可撤销,trash 保留待用户点头再清
5. 重启容器,验证:订阅表无此行 + 该仓库任务 COUNT=0

## node 依赖安装失败 (pnpm PATH 坑, 2026-08-31 实测)

症状: 依赖管理里 python3/linux 都能装, 唯独 node 依赖 1 秒内失败, 日志:
`ERROR The configured global bin directory "/root/.local/share/pnpm" is not in PATH`

青龙 node 依赖走 `pnpm add -g`, pnpm 校验全局 bin 目录必须在 PATH。修复:
```
docker exec qinglong pnpm config set global-bin-dir /usr/local/bin
```
然后重跑依赖安装 (jdpro 的 jd_indeps 任务或面板里重新安装)。
注意: 容器重建后此配置会丢, 需重设 + 重装依赖 (参见 8/5 事件)。

### canvas 原生模块(验证码)完整安装 (2026-08-31 实测)

canvas(node-canvas)是唯一需要原生编译的常用包, 面板安装必失败。alpine 容器完整配方:
```
docker exec qinglong sh -c 'apk add --no-cache cairo-dev pango-dev giflib-dev libjpeg-turbo-dev librsvg-dev build-base python3'
docker exec qinglong sh -c 'pnpm add -g canvas --registry=https://registry.npmmirror.com'   # 约 50s 编译
```
- 面板/全局装的 node 依赖落在 `$(pnpm root -g)`(默认 /root/.local/share/pnpm/global/<n>/node_modules);裸 `node -e "require(...)"` 解析不到, 直测要 `export NODE_PATH=$(pnpm root -g):/ql/data/scripts/node_modules` — 青龙任务环境自带该 NODE_PATH, 所以任务里正常、手动测会"MISS"是假象
- jdpro 的 JDJRValidator_Pure.js 等验证码脚本 require canvas, 装上后滑块验证类任务不再因缺模块挂
- 容器重建后 apk 库 + canvas + pnpm 配置全丢, 需重来 (与上节同一提醒)

## jdpro 全任务 MODULE_NOT_FOUND http2-wrapper (2026-09-01 实战)

症状: jdpro 所有任务秒退, `Cannot find module 'http2-wrapper'`, requireStack 指向 function/dylib.js:1:68834。

根因链: ① 青龙 preload (sitecustomize.js `preferGlobalNodeModules`) 让**全局 npm 包优先**; ② 混淆代码 `require(require.resolve('http2-wrapper', {paths:[require.resolve('got')]}))` 锚定 got 位置找 http2-wrapper; ③ 若全局 got 是 v16 (无 http2-wrapper 依赖, 比如有人 `pnpm add -g got` 不带版本升级了) → 全挂。

修复: `docker exec qinglong pnpm add -g got@11.8.6 http2-wrapper --registry=https://registry.npmmirror.com`。

排查技巧: hook `Module._resolveFilename` 打印 options.paths 看锚点; `require.resolve('got')` 在任务环境(preload激活)与 docker exec 直测结果可能不同。

## wskey 方案:家宽动态 IP 的终极解法(2026-10-02 全流程跑通)

**适用场景**: 家宽动态 IP(联通/电信 PPPoE 不定期换 IP)导致 pt_key 反复被京东作废,手动重抓治标不治本。

### 获取 wskey(手机 VNET 抓包,免 root)
1. 装 VNET(官网已挂,可用 ProxyPin 开源替代 https://github.com/wanghongenpin/proxypin/releases 或旧蓝奏云链接)
2. 点右下角▶ 开始抓包 → 提示安装 CA 证书 → 手机设置里装(搜"证书"→安装 CA 证书)
3. **停止抓包** → 菜单 → 添加应用 → 右上角➕ → 搜"京东"添加(只抓京东流量)
4. 开始抓包 → 京东 App 首页刷新 + 点"我的" + 多点几页(制造流量)
5. 回 VNET 找 **`https://im-x.jd.com`** 或 `https://msg.m.jd.com` 开头的请求 → Cookie 里找 `pin` 和 `wskey`
6. 提取格式(⚠️ **必须带 pin + 英文分号**):`pin=xxx;wskey=yyy;`
7. 换账号:京东 App 退出→换号登录→重复 4-5

### 配置到青龙(实测成功)
1. 环境变量 `JD_WSCK`,多账号用 **`&`** 分隔: `pin=A;wskey=AAA;&pin=B;wskey=BBB;`
2. 任务 `wskey转换`(jdpro 的 jd_wskey.py,每天 11:38)会自动: 读 JD_WSCK → appjmp 接口换 pt_key → 按 pin 匹配更新对应 JD_COOKIE → 自动 enable
3. 手动验证: 启用任务 2335 并 `PUT /api/crons/run` body `["2335"]`,看日志 "WsKey状态正常"/"wskey转换成功"

### ⚠️ 判「wskey 失效」有假阳性: tokenKey=xxx 一律被当失效 (2026-10-02 实测)

jd_wskey.py 的 `appjmp()` 有两条失败分支,含义完全不同:

| 日志字样 | 真实含义 |
|------|---------|
| `pt_pin=X;WsKey状态失效` | 京东 appjmp **真返回了 fake pt_key** → wskey 确实度了 |
| `pt_pin=X;疑似IP风控等问题 默认为失效` | genToken 接口返回 `tokenKey=xxx`(接口拒了这次请求,通常是**同 IP 请求太密/风控**)→ **脚本默认判失效,但是假阳性** |

验证法:把 `jd_wskey.py` 的 `ttotp..appjmp` 函数段切出来单独跑一次(用 `/api/scripts/detail?file=6dylan6_jdpro/jd_wskey.py` 拿全文 → 切出这几个 def → prepend imports+logger+`WSKEY_UPDATE_BOOL=False` → `exec` 后在内存里对每个 pin 调 `getToken()`,**只打印成功/fake,不打印 key 本体**),看命中哪条分支。实测同一批账号:一个返回 fake(真死)、另一个返回 `tokenKey=xxx`(只是接口被拒),而后者对应的 JD_COOKIE **当时仍然活着** —— 所以拿到“疑似IP风控”不能断定 wskey 死了,更不能立刻重试。

**失败分支的日志字样对照**(2026-10-04 实测真失效那一支): `pt_pin=X;状态失效` + `pt_pin=X;WsKey状态失效` + `账号禁用/账号禁用成功`,随后 `WSKEY转换` 段打印 `账号: pt_pin=X; WsKey疑似失效, 已禁用Cookie` 并 `tg 推送成功` → 这串连出来才是**真失效**(appjmp 给了 fake key);注意此时面板 Envs 状态可能并未变(脚本的“禁用”有时只作用于 cookie 匹配,复核 `GET /api/envs` 才算数)。

**外网探针与地面真值同向的一次**: 2026-10-04 从本机探 `me-api` 三条 CK 全 `1001`,随后面板 CK检测(2286)独立判「三条全失效」并自动禁用 —— 说明这次 `1001` 不是被挡;而同一批用 `wq.jd.com/user/info/QueryJDUserInfo?sceneval=2` 探是整片 `403`(该端点对本机 IP 不可用,别拿它判账号死活)。

配套铁律(**2026-10-04 复核日志后改写,原写法是推测**): **不要对同一个账号反复重试 wskey 转换**。原记录写的“16:34/16:49/17:02/22:42 跑 4 次导致两个账号作废” **证据不足** —— 逐个看了当天四份日志,事实是: 前三次是**三个账号各一次、而且三次都成功**(`状态失效 → WsKey状态正常 → wskey转换成功 → 账号启用`,间隔 15 分钟,对应“装好一个账号的 JD_WSCK 就验一次”);22:42 那次是用户贴出 0 豆日报后 6 分钟做的排障,结果账号1/2 `WsKey状态失效`(fake)、账号3 仍 `账号有效`。**没有日志证据能把“这两个 wskey 变废”归因于这 4 次调用**。真正该守的: 失败(`tokenKey=xxx` 或 fake)后**不要立刻重试**,等 24-48h;一次只装/验一个账号,成功即停。

**勘误(2026-10-04 用户纠正): 「未实名」标签不能当事实用**。那条 `(wskey未实名)` 是 **faker 系资产统计脚本**自己印的(`shufflewzc_faker4_main/jd_bean_change.js` 第 671/676、924/929 行)—— 判据是 `if ($.isRealNameAuth)` 这个字段,**取不到该字段就落到 else 分支印「未实名」**(老仓库接口早就取不全,属假命中)。实测的主账号 `ianlee168` 用户说已实名多年。所以: 判“到底实没实名”只能问用户/看京东 App,别照抄日报标签;更不能拿它做“哪个账号比较脆”的归因。另: 该批 3 个账号的 CK 是同一天(2026-10-04)一起判失效的,不存在“未实名先死”。

**jd_wskey.py 失败分支的源码级判定(2026-10-04 读源码确认,以后不用再猜)**:

| 日志字样 | 代码位置/条件 | 含义 |
|---|---|---|
| `X;疑似IP风控等问题 默认为失效` | `appjmp()` 里 `if tokenKey == 'xxx'` | genToken 接口拒了这次请求(**风控/频率敏感性**)——假阳性,可等 24-48h 再试 |
| `X;WsKey状态失效` | 走完 appjmp 后 `if 'fake' in pt_key` | 京东**真返回了 fake pt_key** → 这条 wskey 确实作废 → **再跑一次结果相同,直接重抓,别浪费请求** |
| `X;WsKey状态正常` | 同上 else 分支 | 换出真 key,已自动写回 JD_COOKIE |

另: 脚本会对**每个失效 CK** 都跑这套判定并打印其中一条(不是只看 JD_WSCK),所以“三个账号三行 × 状态失效/禁用”不代表三个账号都配了 wskey。

**替换 JD_WSCK 前先看旧值的“结构”(2026-10-04 实测,值可从 DB 备份取)**: 实测老值是 **三个 `&` 段、每段只有 `pin=..;wskey=..;`**(pin 9/16/15 字符、wskey 各 96 字符,合计 366 字节)——**不含** `whwswswws`/`unionwsws` 等设备指纹 → **“pin+wskey”这个格式足够让 genToken 放行**(2026-10-02 三次成功用的就是它)。取法: `sqlite3 /ql/data/db/full_backup_<ts>.db "select value from Envs where id=20"`,脚本里**只解析并打印 cookie 名与长度**,别把值打出来。⚠️ 改 env 前先确认旧值覆盖几个账号(一脚踩过: 以为只配了一个,实际三个)。另: CK检测日志头部「共 N 个京东账号Cookie」数的是**启用中的 CK 条目**,不是 JD_WSCK 里的账号数。

**同一个账号同一天被拒后不要再手动重试**(2026-10-04 实录: 14:28 拿旧 wskey 换得 `fake`(真失效) → 15:25 用用户当天新抓的 wskey 换得 `tokenKey=xxx`(连 genToken 都没过)) —— 后者**不能判定为新 wskey 有问题**,只是上游拒了这次请求;正确动作是**停手**,让日常任务(11:38 那次)自己试,或等 24-48h。另: 该脚本**只在失败时推通知**(`ql_send` 仅失败分支),成功不推 → “到底成功没成功”得自己去看日志/CK 状态。

### 关键事实
- 换出的是 **App 端 pt_key**(格式 `pp_openAAJq...`,而网页抓的没有 pp_open 前缀),更"原生"
- 验证: me-api.jd.com 返回账号 JSON = 有效;返回 `{"msg":"not login"}` = 失效
- IP 再变化后,下次转换任务会自动重新换 key —— **无需人工干预**,这是相对手动抓 pt_key 的核心优势
- **wskey 本身不会自动续期**(脚本只把新 pt_key 写回 JD_COOKIE,不写回 JD_WSCK)→ 模型是"抓一次用数月,到期/失效后重抓"
- **失效会自动推 telegram,所以不需要用户定期抓**:jd_wskey.py 判断 wskey 换不出 key 时会 `ql_send("账号: <pin> WsKey疑似失效, 已禁用Cookie")`(走青龙 notify → config.sh 的 TG 配置)。用户问"多久要抓一次"的答案:通常 **3-6 个月**,且**等通知**而非定期惦记——收到"WsKey疑似失效"推送再抓一次即可
- **会提前作废 wskey 的操作**: 在京东 App 手动退出登录、改密码(立即失效,别让用户顺手做);风控/长期不用也可能提前失效
- 脚本每次跑先测现有 JD_COOKIE:有效则跳过(不重复转换、不浪费请求),失效才换 —— 所以日志里同一账号时而报"转换成功"时而报"账号有效"都属正常
- wskey 抓取本身也是账号授权操作,有风控风险 — cookie 刚被风控/触发过验证时缓几天再弄

## 京东 cookie 风控教训 (2026-09-08 实战,全量重跑惹的祸)

**症状链**: cookie 刚更新+CK检测全绿 → 全量触发 55 任务(手动全跑)→ 9 分钟后 CheckCK 报全部失效 → 后续重抓触发面部识别验证(风控升级)。

三层根因 + 铁律:
1. **换新 cookie 后禁止 `PUT /api/crons/run` 全量触发**(55 个脚本瞬间并发几十个接口=典型 bot 特征)。验证只单跑 CK 检测(2286),其余让任务按各自 schedule 自然跑——青龙本来就把时间错开了。
2. **代理/IP 漂移是隐藏雷**: 调试软路由(PassWall/openbox)换出口 IP 会让京东给账号打风险标记,标记存在时新 key 遇任何异常流量(如全量并发)立即作废。京东域名已在 PassWall Direct 规则强直连防再漂移;「流量是否真走代理」的诊断法与加规则步骤 → 见 `references/passwall-proxy-diagnosis.md`。
3. **触发面部识别/滑块验证 = 风控升级信号**: 立即停止一切登录/抓取操作,等 24-48h 让标记消退,别反复重抓(越抓越可疑)。
4. **家宽动态 IP 是不定时炸弹(2026-09-11 实测确认)**: 北京联通 PPPoE 家宽每次重拨/路由重启都会换 IP(实际观测 123.114.192.101 → 111.194.59.132),京东对登录 IP 变化敏感,叠加风控观察期会把 cookie 作废。检查方法:路由器 `ifstatus wan` 看 IP + 与上次记录对比;应用侧 `docker exec qinglong curl -s https://myip.ipip.net`(国内回显服务,别用外国的会显示代理出口)。IP 不可控 → 正解是 **wskey 方案**(wskey 是 App 长期凭证,IP 变化导致 pt_key 失效后能自动换新,免人工重抓),青龙已有 jd_wskey.py/jd_wsck.py 任务,只差 JD_WSCK 环境变量(格式 wskey1&wskey2);手机抓包流程、工具选择与证书坑 → `references/jd-wskey-capture.md`。

诊断要点: key "9分钟前全绿现在失效" 不是 key 本身问题,查环境(代理/并发/IP)而非重抓。

## .py 工具连不上青龙 API (IPPORT/端口坑, 2026-09-01 实测)

jdpro 的 .py 工具 (jd_taskop.py 重复任务优化 / jd_wsck.py / jd_wskey.py) 要连青龙 API 管理任务/env, 失败特征:
`requests.exceptions.ConnectionError: HTTPConnectionPool(host='127.0.0.1', port=6700/5600)`。

两层原因 + 修复:
1. **config.sh 的 IPPORT 被设成宿主端口**: 宿主机 `/mnt/user/appdata/qinglong/config/config.sh` 里 `export IPPORT='127.0.0.1:6700'` — 容器内青龙监听的是 **5700** 不是 6700。改回 `export IPPORT='127.0.0.1:5700'`(改前 cp 备份)。脚本读 `os.getenv("IPPORT")`。⚠️ **清理 config.sh 死 export 时 IPPORT 必须保留**(它在文件尾部 export 区,容易被误当死变量删掉;2026-09-09 实测误删过,后果是 wsck/wskey/taskop 等 .py 工具全连不上 API)。
2. **硬编码旧端口**: 某些脚本写死 `127.0.0.1:5600`(老青龙默认), 需 sed 批量替换为 5700 (如 jd_wsck.py)。

## 全量依赖体检 (触发全部任务 + 扫日志, 2026-09-01)

用户想知道"还有什么依赖缺失"时: 一次触发所有任务 (`PUT /api/crons/run` body=[id1,id2,...] 全部 id, 青龙自带并发队列), 等几分钟后扫 log 目录找 `Cannot find module` / `ModuleNotFoundError`。复用脚本: `scripts/scan_jdpro_logs.py`(在容器内跑: `docker exec qinglong python3 /ql/data/scripts/scan_jdpro_logs.py`, 路径写死 /ql/data/log; 注意日志目录名有时带任务ID后缀有时不带, 以 ls 为准)。

⚠️ 刚更新/重抓 JD_COOKIE 后**禁止**批量 run 全部任务 — 新 key 全量并发会被京东风控作废且无法恢复,只能重抓。详见「京东 cookie 风控教训」节;依赖体检要用批量 run 时,先确认 cookie 非新抓且已跑稳。

## 安全审计 / 要不要重装 (2026-09-01 实战)

用户看到 jdpro 横幅警告("青龙2.20.2以下版本不要外网访问, 已被爆破可任意登录")问要不要推倒重装 → 三步审计: 版本号 + 公网暴露(路由器 DNAT/ddnsto) + 入侵痕迹(只读查 database.sqlite: Auths 登录日志 / Apps / Crontabs.createdAt)。含结论模板、重装保数据事实、本机审计基线 → **`references/security-audit.md`**。

判断口诀: 版本 ≥2.20.2 + 纯内网 + 无植入 = 没必要重装; 数据全在 bind mount 宿主机目录, 重装只丢容器内依赖(可重装)。

## 区分脚本 bug 与环境问题 (对照实验, 2026-09-01)

某任务 3 账号同位置确定性报错(如 jd_vu50 超市卡 "Cannot read properties of undefined (reading 'pipeExt')", 混淆代码查无此串), 先分清是上游脚本 bug 还是我们依赖环境搞坏的:
```
# 脱离青龙任务环境直跑: 无 preload(sitecustomize 全局优先), 只用本地 node_modules
VAL=$(curl -s http://192.168.50.1:6700/api/envs -H "Authorization: Bearer $TOKEN" | python3 -c "...取第一条 JD_COOKIE value...")
docker exec -e JD_COOKIE="$VAL" -w /ql/data/scripts/6dylan6_jdpro qinglong node jd_vu50.js
```
错误照旧 → 脚本/上游问题(等作者更新或禁用); 错误消失 → 全局依赖干扰(查全局 got 等版本)。

## 依赖体检(哪些能删,2026-09-09 实测 77→35)

Dependences 表里大量历史“账单”记录 ≠ 实际安装。判定:
- **实际安装位置**: node 面板依赖装到 `$(pnpm root -g)`(如 /root/.local/share/pnpm/global/5/node_modules);记录删不删不影响已装包,删前先确认包本体 OK(手动 `pnpm add` 过的 2026 记录才是 jdpro 真实依赖)
- **明显垃圾记录**: 非 npm 包名(magic/world/jd_sign/depend/function/common)、Node 内置模块(fs/require)、Python 包误加到 node 类(requests/prettytable/jieba/ql)、名字带 "-g"、带版本号旧记录(ws@7.4.3)、重复安装记录(同包 2023+2026 各一条)
- **删除姿势**: 备份 `.backup deps_backup_<ts>.db` → `DELETE FROM Dependences WHERE type=0 AND createdAt LIKE '2023%'` → `SELECT changes()` 验证。type: 0=node 1=python3 2=linux。python3/linux 记录和 2026 的 node 记录(jdpro 依赖)保留

## 脚本通知(telegram)失败排查:假代理 → 死 token 两层

jd_CheckCK 等任务跑完报 `telegram发送通知消息失败` + `RequestError: tunneling socket could not be established / connect ECONNREFUSED 127.0.0.1:1081` — 两层原因按序查,别修完第一层就收工:

1. **假代理(第一层)**: `/ql/data/config/config.sh` 里 `TG_PROXY_HOST=127.0.0.1` + `TG_PROXY_PORT=1081` 指向容器内不存在的代理。容器通常能直连 telegram(验证:`docker exec qinglong curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://api.telegram.org` 得 302 即通)→ cp 备份后把两个 export 置空即可;sendNotify.js 只在两值都非空时走代理,脚本下次跑即生效,不必重启容器。
2. **bot token 被 revoke(第二层)**: 置空代理后仍失败且报 `Response code 401 (Unauthorized)` = token 死了,改配置无用。验证:`docker exec qinglong sh -c "set -a; . /ql/data/config/config.sh; set +a; curl -s https://api.telegram.org/bot\${TG_BOT_TOKEN}/getMe"` → `{"ok":false,...401}` 即死 token,只能让用户在 @BotFather → /mybots → API Token → revoke 后重新生成新 token 填回。
   ⚠️ **反向也要成立,别只凭一条 401 就提议换 token**: 实测全库日志 24h 内只有 2 行 `401`,来自某个 JD 任务(与通知无关),而同一时刻 `getMe` 返回 `ok:true`、容器内 `sendNotify()` 实测打印 `Telegram发送通知消息成功🎉` —— 若照“看到 401 就是 token 死”处理,就会白做一次凭证轮换。判死顺序固定: **① `getMe` 看服务端真值 → ② 真发一条看响应体 `ok:true` → ③ 才谈轮换**;也别把别的会话/别的服务的“token 失效”结论直接当事实(第三方容器遇到 401/429 常常静默丢包)。这个 bot 被多个服务共用 → 真要轮换必须**两处同改**(青龙 `config/config.sh` + 对应容器 env)且旧值立即失效。

其他注意:
- 青龙自己的 `config/bot.json`(telegram 遥控青龙用)与脚本通知无关,里面 user_id/bot_token 常是占位符,别拿它当有效凭据排查
- 手动测整条链路:容器内 node 脚本 `require('<repo>/sendNotify.js').sendNotify('标题','正文')`,先 `export NODE_PATH=$(pnpm root -g):/ql/data/scripts/node_modules` 并 source config.sh 注入环境变量再跑
- **sendMessage 429 限流**: 连续测试/补发会触发 `Too Many Requests: retry after NNN`(数百秒),且每次重试刷新冷却窗口——收到 429 就停手等 retry_after 自然归零,别循环重试(越试等越久)。日常 cron 每天 1-2 条远低于阈值;验证链路优先用 `getMe`(查 token 有效性,不占消息配额),发消息只测一条
- 同一 bot 可被多个服务共用(青龙通知、MS Rewards 日报等),token 从 config.sh 的 TG_BOT_TOKEN 读,别在每处硬编码副本

## 其他服务共用青龙 telegram bot

MS Rewards 签到容器等其它 cron 服务要推 telegram 时,复用青龙 config.sh 的 TG_BOT_TOKEN/TG_USER_ID(读文件注入,别复制 token 到多处)——用户一个 bot 收全部通知。容器化第三方签到工具(浏览器自动化型)的部署/运维 → skill `microsoft-rewards-automation`。

**推送纪律(用户明确要求)**: 用户要的是**每天 1-2 条汇总**(状态 + 余额/结果 + 较昨日变化),不是逐条日志。第三方容器常见默认行为是**每一条日志各发一条 TG**(搜索得分 +3、失败各一条),接之前先查并关掉它的通知开关;共用同一个 bot 时,任何一个服务刷屏都会让用户把全部通知都嫌吵。

## 面板「运行中」永久转圈 = status/pid 残留 (2026-10-02 实测修复)

症状: 一批任务的「状态」列一直转圈显示运行中(用户会说"以前不这样"),但 `docker exec qinglong ps -eo pid,etime,args` 里毫无对应进程。

定性(先分清「胶囊」的两个来源,别猜):
0. **面板「状态」列的胶囊由 `RunningInstances` 表(运行实例记录)决定,不是 `Crontabs.status`**。`RunningInstances(cron_id,pid,log_path,started_at,finished_at,status,exit_code)` — `status=1` = 运行中,其余档位(正常结束等)不显示。**只清 `Crontabs` 的 pid/status 往往对页面完全无效**(实测: 清完用户仍看到一片「运行中」),必须先 `select status,count(*) from RunningInstances group by status;`,把 `pid` 在容器内 `/proc/<pid>` 查不到的 `status=1` 行标成「已结束」那一档,胶囊即消失。任务结束回调**静默失败**时会不断长出新残留: 面板容器重启后 `/ql/data/config/token.json` 与它内部 app 令牌错位,结束回调 `PUT /open/crons/status` 收 401 而日志里什么都不打 → 先修令牌,否则清完还会再长。
1. 容器内无脚本进程 = 面板显示的是残留,不是真在跑。
2. 直读库 `SELECT id,name,status,pid,isDisabled,last_execution_time,updatedAt FROM Crontabs` — 残留特征: `pid` 非空且该 pid 在宿主机/容器都不存在、`status=1`;若 **updatedAt 成片毫秒级相同**(如 59 行同一时间戳),说明是某次批量状态写入(开放 API 全量 run、或误用数字 id 的批量 disable)留下的,任务完成回调没跑。注意 `last_execution_time` 存的是**秒**(不是毫秒),换算时别除 1000 把日期算成 1970。

修复(先备份再改):
- 可撤销前置: 把 `id,name,command,schedule,status,pid,isDisabled,last_execution_time,last_running_time,updatedAt` 导成 TSV 快照 + 用 sqlite3 的 backup API 生成 `full_backup_<ts>.db`,都丢 `/ql/data/db/`(宿主机 `/mnt/user/appdata/qinglong/db/`)。
- 复位(**值别写反**): `UPDATE Crontabs SET status=<目标态>, pid=NULL, queued_token=NULL WHERE id=?` — 只清「`/proc/<pid>` 查不到」的行(命中即跳过),`status` 按任务目标态写字面值: 该任务启用→**`1`(空闲)**,该任务停用→**`2`(禁用)**。**绝不写 0**: 0 是「运行中」,写 0 等于把症状原样复现——同一坑两个 agent 各踩一次(修复脚本里的 `SET status=0` 直接让用户看到"还是很多运行中")。动手前先花 10 秒从源码确认枚举,别照抄任何现成脚本里的字面值。
- 不用重启容器(面板按请求读库)。
- **没有宿主机 ssh 时的修复路径(2026-10-02 实测通过)**: 用 `/api/scripts` POST 写一个修复脚本到 `/ql/data/scripts/`,脚本自己 `sqlite3.connect("/ql/data/db/database.sqlite")`、**逐行用 `os.path.exists("/proc/<pid>")` 在容器内验活**(别信面板的 pid 字段),先 `shutil.copy2` 备份 DB 到 `/ql/data/db/full_backup_<ts>.db`,再只对 `alive=False` 的行 `UPDATE Crontabs SET status=0,pid=NULL` → 建临时 cron 任务(占位 schedule)`命令=python3 /ql/data/scripts/_fix.py` → `PUT /api/crons/run` → 日志读 `log/python3/<时间戳>.log`。
- 日志目录名 = **命令行的第一个词**(`python3 /ql/data/scripts/_fix.py` → 日志落在 `log/python3/`;`task xxx.js` → 落在 `log/<仓库名>_<脚本名>/`),按这个找目录。
- 坑: 临时修复任务自己的行清不掉 —— 三招都试过、都没用: ① 脚本里补一条 `UPDATE ... WHERE id=<自己>`(运行器在进程退出时又写回 status=1 + 新 pid); ② `PUT /api/crons/disable`+`/enable`(行原样不动,status/pid 不变); ③ `/api/crons/status`(它是 setter,body 必须带 `{id,status}`,不是查运行态的接口)。**唯一办法是删掉这个临时任务** → 修完就把临时任务删掉(删除红线:先问用户),别留在面板上永远转圈。
- **修完必须同时管住“用户屏幕上会看到什么”,否则用户会回一句“还是运行中啊”**: 面板任务列表是**一次性拉取、不自动刷新** —— 修复前打开的页面会一直显示旧行。所以答复里直接给出「Ctrl+F5 强刷」,并把临时修复任务自己那条必然存在的“运行中”提前说明(它的存在是预期,不是没修好)。
- **判断“修没修好”只看 `/api/crons`,不看页面**: API 已干净而页面还转圈 = 页面未刷新,不是修复失败。若用户硬刷后 API 干净而页面仍有一批“运行中”,才是面板进程里的内存态残留 → 重启青龙容器;先搞清容器到底跑在哪台机器(面板 URL 可能是 DNAT/反代,别把面板 IP 当成 docker 宿主机)。
- 现成脚本: `scripts/ql_stale_status.py`(纯 stdlib,`--check` 列残留 / `--fix` 自动部署修复脚本 + 跑临时任务 + 复核)。
- 复核必须走 API 而不是只看库: `GET /api/crons` 的返回形状是 **`data.data[]` + `data.total`**(不是 data 直接为数组);看用户点名任务的 `pid` 是否 null、`status` 是否 0。

## 「运行中」残留的真根因:令牌每日漂移 + 自愈任务 (2026-10-04 实测)

清完 `RunningInstances` 第二天又长出来时,别只怪“面板重启”——根因是: **面板每天 08:00 自换内部 system 令牌**(判据: `Apps.id=1 name=system` 的 `updatedAt` = 当天 `00:00:01 UTC` = 北京 08:00;`token.json` 的 `expiration` = 生成时刻 **+30 天**),但磁盘上的 `/ql/data/config/token.json` **不跟着更新** → 当天 08:00 之后每一个跑完的任务,结束回调 `PUT /open/crons/status` 全部 **401 且静默** → 每个完成的任务留一行 `status=1` 的假「运行中」。

- **判令牌死活别看 expiration 字段**(实测文件里 expiration 还写着 11-02,认证却已 401)——唯一判据是**拿它打一次**:`TOK=$(python3 -c "import json;print(json.load(open('/ql/data/config/token.json'))['value'])")` → `curl -s -o /dev/null -w %{http_code} -H "Authorization: Bearer $TOK" http://127.0.0.1:5700/open/crons` → **200 活 / 401 已漂移**。
- 令牌是**不透明 36 字符串**(不是 JWT,段数=1),别按 JWT 去解 payload。
- **修**: 跑面板自带生成器 `node /ql/static/build/token.js`(它用 `{value,expiration}` 覆写 token.json;`require` 是 file-relative,任意 cwd 都能跑)→ 再探应 200;验写入权限用伪 id `PUT /open/crons/status` 得 **400**(鉴权已过)而不是 401。
- **自愈任务**(已建,id 会变、按名字找): 名字「令牌同步(修运行中残留)」、命令 `node /ql/static/build/token.js`、排期 `5 8 * * *`(面板 08:00 换令牌后 5 分钟)。新建的形状: `POST /api/crons` 单对象 `{"name":..,"command":..,"schedule":..}`。
- **必须造真故障测**(用户明令): 备份 `token.json` → 写一个 36 字符假值进去 → 探 `GET /open/crons` 应 **401** → `PUT /api/crons/run ["<id>"]` → 25 秒后再探应回 **200**(实测任务 1 秒跑完)。只“建了任务没测”不算完成。
- **残留复位的正确字面值**: `RunningInstances` 里 `status=1` 才是「运行中」,**已结束是 `status=3`**(`exit_code` 0=成功 / 1、3=失败;2=未知)→ 清残留写 `UPDATE RunningInstances SET status=3, exit_code=0, finished_at=<now>`;`Crontabs` 侧同前(启用→1、停用→2、`pid=NULL`)。

## YYB-Go 账号失效 → 分享版脚本集体挂 (2026-10-02 实测)

症状: 阿维塔 + 捷停车 同时失败,脚本日志 `HTTP Error 502: Bad Gateway`(请求 `/wxapp/getCode`)。

判据链(一次查清,别只测端口):
- YYB-Go 容器日志 `keepalive: account id=N refresh failed: refresh failed: code=-109 msg=RC_PARAMS_INVALID`(每 6 分钟一条);`grep -c` 看规模、`grep -n` 首条 = 失效起始时刻(本例 09-30 16:43,此后一直没恢复)。
- 管理 API 复核: `POST /login` 取 cookie → `GET /accounts` 看 `status`(alive/unknown);`POST /accounts/refresh {"ref":"<openid>"}` 回 `status=unknown` + `refresh_error=...RC_PARAMS_INVALID`。**`POST /accounts/resync` 救不回来** — resync 后 `rescan_recommended=true` 即只能重新扫码。
- 宿主机 curl `:8000/` 得 303、`/health` 得 200 会被误判成"服务正常";从青龙容器打 `/wxapp/getCode` 得 502 才是真信号(与网络无关,是上游凭据死了)。

修复 = 用户手机重新扫码。**可以直接把二维码递到聊天里**,不必让用户开面板:
- `POST /qr` body `{}` → `data.session_id` + `data.image_url` = `/qr/<sid>/image`
- `GET /qr/<sid>/image` = 二维码 JPEG(约 40-50KB);`GET /qr/<sid>/poll` 查扫码状态 —— 未扫时返回 502 `context deadline exceeded`(长轮询超时),别当故障。
- 同一 openid 重扫会**更新原账号记录**,脚本 config.json 里的 openid 不用改;扫完用户要在手机上确认。
- 二维码有 TTL,递给用户前现取一张新鲜的。
- 上游仓库有 `明确过期凭据账号需重新扫码` 一类提交,说明这就是官方预期处置方式;容器镜像老(如 08-31 构建)时可顺带 `git pull` 重建,但重扫才是根治。

**分享版脚本依赖在容器重建后会丢**: 捷停车报「JWT库错误」其实是 jwt 模块压根没装(`pip3 uninstall jwt` 会说 not installed)→ 装 `pyjwt`;其余自检依赖 `httpx[http2] httpx-socks python-dotenv pycryptodome` 一并 `pip3 install ... -i https://pypi.tuna.tsinghua.edu.cn/simple`。装完仍 502 = YYB-Go 账号问题,不是依赖。

## Pitfalls

- **API 建/改任务带中文名必须用 UTF-8 文件提交**: Windows bash 命令行里 -d '{"name":"中文"}' 会被终端编码搞成乱码存进库里 (2026-08-31 实测 2283/2284 两任务名变 ��ά��ǩ��)。正确姿势: write_file 写 JSON 到临时文件, curl --data-binary @file。更新任务 PUT /api/crons 要完整对象 (id+name+command+schedule)。

- **DNS 陷阱**: `50.1` 主机名在不同上下文解析到不同 IP（见 references/dns-quirks.md）。用 IP `192.168.50.1` 最可靠。
- **登录状态**: API 需要 Bearer Token，未认证返回 401。浏览器访问需要登录。
- **curl 超时**: 容器启动慢，`curl` 可能 timeout，需要加大 timeout 参数。

## 文件索引

- `references/dns-quirks.md` — 50.1 DNS 解析陷阱详解
- `references/third-party-signin-scripts.md` — 部署第三方多平台签到脚本库(ql-script-hub 类): 按平台筛选、子目录 + notify.py、依赖/变量名自检、建任务 API 形状、随机延迟
- `references/jd-wskey-capture.md` — 手机抓京东 wskey 填 JD_WSCK:抓包工具选择(ProxyPin 开源 vs 老 VNET)、CA 证书/pinning 挡住的判据、多账号 `&` 格式、填值与单跑验证
- `references/passwall-proxy-diagnosis.md` — 判断容器流量是否真走代理(国内外 IP 回显对比)+ PassWall 域名强制直连步骤(京东风控根因排查用)
- `references/yyb-go-wechat-login.md` — YYB-Go(微信登录)部署 + 阿维塔/捷停车签到两案例:风控110000根因(绑错微信)、JWT字段漂移、config.json子目录隔离、静默失败调试法(2026-08-31)
- `references/security-audit.md` — 青龙安全审计三步法(版本/暴露/入侵痕迹) + 2.20.2 红线含义 + 重装保数据事实 + 本机基线(2026-09-01)
- `scripts/ql_stale_status.py` — 「运行中」残留体检/复位(无需宿主机 ssh): 列出 `pid` 非空或 `status=0`(运行中)的行,`--fix` 则在容器内逐行 `/proc/<pid>` 验活、备份 DB、把"进程已不存在"的行复位成 `status=1`(该任务启用)/`2`(该任务停用)+`pid=NULL`,并打出后续必做项(硬刷页面/删临时任务)