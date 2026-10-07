---
name: microsoft-rewards-signin
description: Use when 维护 Rewards 签到容器(Unraid docker)。登录失败排查、开关、日报。
tags: [docker, unraid, microsoft, rewards, bing, signin, telegram]
---

# Microsoft Rewards 自动签到容器 (Unraid)

## 用户环境

- 容器: `microsoft-rewards-script`(Unraid 50.1,docker compose 部署,**不在 CA 模板里**,UI 只能启停,别点 remove)
- 代码: `chiihero/Microsoft-Rewards-Script`(国内本地化;上游 TheNetsky/Microsoft-Rewards-Script)
- 路径: `/mnt/user/appdata/microsoft-rewards/app/`(compose.yaml + docker-compose.override.yml;compose 项目工作目录在此,`docker compose up -d` 要 cd 进去跑)
- 凭据: gbrain `credentials/microsoft-ianlee168`;TG 推送复用青龙 bot(读 `/mnt/user/appdata/qinglong/config/config.sh` 的 TG_BOT_TOKEN/TG_USER_ID)
- 调度: 容器内 cron 每天 07:00(CRON_SCHEDULE);启动时 RUN_ON_START 立即跑一次

## 部署/重建

```bash
ssh root@192.168.50.1
cd /mnt/user/appdata/microsoft-rewards
mkdir -p app/config app/sessions
cd app && docker compose build && docker compose up -d
```

- 账号在 `.env`:`ACCOUNT_1_EMAIL` / `ACCOUNT_1_PASSWORD`(可多账号 ACCOUNT_N_*;国内加 `ACCOUNT_1_LANG_CODE=zh-CN` `ACCOUNT_1_GEO_LOCALE=CN`)
- **改 .env 后必须 `docker compose up -d --force-recreate`** — env_file 只在容器创建时读,`docker start`/`restart` 不重读配置!(实测密码改了 restart 不生效)
- 验证生效:`docker exec microsoft-rewards-script sh -c 'echo "$ACCOUNT_1_PASSWORD"'` 看值/长度

## 稳妥版配置(只签到+连击+领积分,关搜索防封号)

写在 `docker-compose.override.yml` 的 environment 段(别改 compose.yaml 本体,升级会覆盖):

```yaml
services:
  microsoft-rewards-script:
    environment:
      CONFIG_ENSURE_STREAK_PROTECTION: 'true'
      CONFIG_WORKER_DAILY_CHECKIN: 'true'
      CONFIG_WORKER_CLAIM_BONUS_POINTS: 'true'
      # 其余 worker/activity 全关:DAILY_SET MORE_PROMOTIONS PUNCH_CARDS
      #   APP_PROMOTIONS DESKTOP_SEARCH MOBILE_SEARCH BONUS_SEARCHES
      #   READ_TO_EARN ACTIVATE_SEARCH_PERK VISUAL_SEARCH URL_REWARD SEARCH_ON_BING
      # Telegram 日报:CONFIG_TELEGRAM_ENABLED/BOTTOKEN/CHATID(注意无 WEBHOOK 前缀)
```

- 覆盖变量名 = config.json 点路径大写化(ConfigEnvOverrides.js 定义);验证看 entrypoint 日志 `Applied N override(s)`
- 搜索类任务(doDesktopSearch/doMobileSearch)是封号风险主要来源,默认别开

### 得分结构:为什么一天只有个位数(用户会问"是不是有点少")

- 稳妥版只剩 签到 + 领奖励积分 + 连击保护 ⇒ **实测 5-15 分/天**。不是上游脚本坏了,是配置只留了基础分。
- 日得分查容器日志 `RUN-END` / `ACCOUNT-END` 行:`获得积分=N | 原余额=A | 现余额=B`。
- 分数主力是**搜索类 worker**(桌面搜索 / 移动搜索 / 阅读赚分),稳妥版把它们全关了,所以只有个位数。
- 开启(用户批准后):把 `CONFIG_WORKER_DESKTOP_SEARCH` / `CONFIG_WORKER_MOBILE_SEARCH` /
  `CONFIG_WORKER_READ_TO_EARN` 置 `'true'` → **先 cp 备份 override** → `docker compose up -d`(重建容器;
  重启即 RUN_ON_START 跑一轮,当场就能看到搜索流程被触发)。
- **先只开这三项**,促销 / 打卡卡 / 视觉搜索 / 额外搜索继续关;跑几天看日志里的 `疑似受限` / `bot标记` /
  `serpbotscore` 再决定要不要加。CN 区账号搜索分可能明显低于美区,以实测为准。
- 回退:取 `docker-compose.override.yml.bak-*` 覆盖后 `docker compose up -d`。

## 登录失败排查(最常踩)

- **Windows PIN ≠ 账号密码**: PIN 绑设备(TPM),容器里永远无法用 PIN 登录;要真实微软网页密码,让用户浏览器 account.microsoft.com 验证/重置
- 密码错误报 `ERROR_ALERT` + "此密码不是你的 Microsoft 帐户的正确密码";用户易把 `!`/`?` 结尾记混,别瞎猜,让用户重置最稳
- **连续错密码 → 账号临时锁**: "使用不正确的帐户或密码尝试登录的次数过多" = 微软节流,等 15min+;期间**停容器**(cron 07:00 会再撞锁),也别用浏览器反复试
- 登录页显示"批准使用移动应用登录"在首位 = 账号无密码化(passwordless),优先 Authenticator——容器不支持交互批准,需先关无密码或走密码流
- 残留会话干扰重试: 删容器内 `/usr/src/microsoft-rewards-script/sessions/sessions.db` 强制全新登录(先 docker stop)
- 成功标志: 日志 `状态转换: ... → LOGGED_IN` + `登录成功` + `[DAILY-CHECK-IN] 每日签到完成`
- 锁定期内**任何**登录尝试都会延长锁定,明确告诉用户"等 N 分钟别动"

## 新故障模式(2026-10-06 起实测): FIDO/passkey 拦截 → “应用活动被跳过” → 签到消失

**症状**: 日报连着几天 `❌ 未见签到记录`,但余额仍在小幅上涨(+60~200/天),看着像“半好”。

**判据(看原始日志,别只信日报措辞)**: `docker logs --since 72h microsoft-rewards-script 2>&1 | grep -aE "验证Bing会话|fido|LOGIN-APP|每日签到"`
- 正常: `[LOGIN-BING] 在Bing页面: true (cn.bing.com/)` → 随后有 `[MOBILE] [DAILY-CHECK-IN] 每日签到完成`
- 故障: 验证循环 1/5~5/5 每轮 URL 都是 **`login.microsoft.com/consumers/fido/get`**、`在Bing页面: false` → 随后
  `[WARN] [LOGIN-BING] 无法验证Bing会话，继续执行` + **`[WARN] [LOGIN-APP] 无法解析移动OAuth代码 - 本次运行将跳过应用活动`**
  → 签到属于“应用活动” → **整条被跳过**(日志里连“开始每日签到”都没有 ⇒ 日报的 ❌ 是**准的**,不是误报)。
- 余额仍涨的原因: DESKTOP 平台的搜索类活动照跑(日志 `[QUERY-QUEUE] 聚类已激活 | 主题=...`)+ 领积分 → **只有签到这一路断**。

**根因**: 该账号注册了 **passkey**(人脸/指纹/PIN/安全密钥)或开了“无密码登录”——登录方式列表出现“使用人脸、指纹、PIN 或安全密钥”。容器无法完成交互式 FIDO/批准验证。

**处置(让用户选)**: ① 在 account.microsoft.com → 安全性 → 高级安全选项里**删除 passkey / 关闭无密码账户**(回到密码流,签到即恢复;代价=用户自己也不能用 passkey 登录); ② 保留 passkey ⇒ 自动签到基本无解(只能等上游支持或放弃)。

⚠️ 同期的独立问题: DESKTOP 密码登录可能报 `此密码不是你的 Microsoft 帐户的正确密码`(密码被改 / 账号已被强制无密码化)。改 `.env` 后必须 `docker compose up -d --force-recreate`;连续错密码会被锁 → 确认密码前别反复试,必要时**先停容器**(cron 07:00 会再撞)。
⚠️ 日报脚本的判定式: 最近 24h 内 grep `每日签到完成.*pointsGained=[1-9]` → 不匹配就报 ❌。所以“签了但 0 分”也会显示 ❌;遇到 ❌ 必须回原始日志区分“真没跑”还是“跑了 0 分”。

## 日志判读

- `docker logs --since 24h microsoft-rewards-script | grep -aE 'DAILY-CHECK-IN|RUN-END|LOGIN'`
  (**`--since` 只认 s/m/h**,`--since 6d` 静默无效;要几天就换算 `--since 168h`。中文日志建议带 `grep -a`)
- 会话可能跨天:判读日志/排期前先跑 `date` 确认真实当前日期,别拿会话开始日当"今天"
- 签到成功:`每日签到完成 | type=103 | pointsGained=N`;当天重复跑 `pointsGained=0` 属正常(已签过)
- 余额: RUN-END 行 `现余额=N` 最可靠(DEBUG 行 currentBalance 也可)
- 领积分(claim bonus points)是签到外的另一笔(+63 常见),都会计入 RUN-END 现余额

## 每日日报 + 异常告警

- Unraid `/root/check_msr_signin.sh` + cron `0 8 * * *`(crontab -e,别用 /etc/cron.d/ 不生效)
- 逻辑: 从容器日志取最近 `现余额` → 与 `/root/msr_balance.state` 上次值算日变化 → 拼 🎁 日报推 TG → 更新 state
- 日报含: 签到状态 + 当前余额 + 📈/📉 较昨日;成功不告警,异常(无登录/签到记录)单独推 ⚠️
- 日志落 `/root/msr_signin_check.log`
- **"用户说没收到日报"先查三件事,别假设它已部署**:①`ls -la /root/check_msr_signin.sh`(台式机上的副本
  ≠ 已部署到 50.1);②`crontab -l | grep msr`;③`cat /root/msr_signin_check.log` 有无近期记录。
  实测曾三样全无 —— 脚本只在 Windows 上留了个副本,日报从未跑过,而 skill 里写着"已部署"。
- **发送成功必须看响应体,`[TG-SENT]` 会假阳性**:`curl` 不带 `-f`/`--fail` 时,HTTP 4xx 或 API
  `ok:false` 也返回 exit 0,旧写法 `curl … && echo [TG-SENT]` 会把失败记成成功。判定式:把响应体接住,
  `grep -q` 断言含 `"ok":true` 才算成功,否则把响应体前 300 字符写进日志(记成 `[TG-FAIL] …`)。
- 文本含中文 / emoji / 换行时用 `curl --data-urlencode "text=$MSG"`(`-d` 不做编码);MSG 用双引号
  跨行字面量写即可保留真换行,不要写成字面的反斜杠-n。

## Pitfalls

- **改 .env 必须 force-recreate**(见上)—— 最常见的"改了没生效"
- **telegram 429 限流**: 短时间连发测试消息会 `Too Many Requests: retry after N`;别连环重试,等 N 秒再发。生产每天 1-2 条不会触发
- 容器内无 python3;读配置用 docker cp 到青龙容器(qinglong 有 python3)或宿主机无 python 时绕道
- 密码含 `!`/`?`/`!!` 等特殊字符在 .env 里直接写即可,compose 能正确读(别加引号转义)
- 手动 `docker stop` 后 restart policy unless-stopped 不会自动拉起——锁定期手动停的,解除了要手动 start
