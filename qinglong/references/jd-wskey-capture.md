# 手机抓京东 wskey(填 JD_WSCK,让 pt_key 自动续期)

何时用:家宽动态 IP / 风控导致 pt_key 反复失效(如北京联通 PPPoE 重拨换 IP),用户不想每 30 天手动 F12 抓 cookie。jd_wskey.py 用 wskey 换新 pt_key 并自动写回 JD_COOKIE,一次抓取长期免维护。

## 工具选择

- 首选 **ProxyPin**(开源,GitHub `wanghongenpin/proxypin` releases 直接下 `proxypin-android-arm64-<ver>.apk`;VPN 模式免 root;持续更新,不怕官网失联)。本机可直接下载 APK 再 `MEDIA:` 发给用户装(手机若上不了 GitHub 就别给用户 GitHub 链接)
- 次选 VNET / Stream / HttpCanary 等老工具 —— 官网/商店常失效,第三方下载站的包不可信;找不到官方源就别硬装。且 VNET 停更已久，对高版本安卓 VPN Service 与 TLS 1.3 兼容差，易导致整机/应用网络黑洞
- 电脑端 mitmproxy 对**无 root 安卓没用**(Android 7+ 不信任用户证书,京东 App 另有证书校验),别让用户往这条路上走

## 抓取流程(手机 App,VPN 模式免 root)

1. 装 APK → 打开 → 起抓包(系统弹 VPN 授权 → 允许)
2. 按引导**安装 CA 证书**到「用户凭据」(设置 → 安全 → 加密与凭据 → 安装证书 → CA 证书);工具里显示"已安装"才算好
3. 切到京东 App:任意商品**加入购物车**(多点几次),或下拉刷新「我的」页 —— 这两个动作会带 wskey
4. 回抓包工具,请求列表搜 `wskey` → 命中请求里取 `pin=xxx;wskey=xxxxx;`
   - 直接找 **`https://im-x.jd.com`** 或 **`https://msg.m.jd.com`** 开头的请求更快(这两个域名的 Cookie 里就有);老 VNET 教程也是指这两个
   - ⚠️ 必须带 `pin=` 前缀:只给 `wskey=xxx` 会被判格式错(脚本靠 pin 匹配账号)
   - ⚠️ **wskey 长度必须为固定 96 位**: 若收到 70~80 位（如 75 位）说明抓包工具预览截断或复制未到底，必须让用户完整复制到末尾分号
5. 每个京东账号各抓一份(不同账号 = 不同登录态,分别抓)

## 填进青龙

- JD_WSCK 值:多账号用 `&` 连接(`wskey1&wskey2&wskey3`),单账号直接写一段
- env 不存在先建:`POST /api/envs` body 包数组;**value 不能为空**(空值 400 `"[0].value" is not allowed to be empty`)→ 先放占位串再改成真值
- 没填真值前先 `PUT /api/envs/disable` 禁用,免得任务空跑
- 填好 → `PUT /api/envs/enable` → **单跑 jd_wskey 任务**验证:日志 `WsKey状态正常` + 随后 JD_COOKIE 被自动更新 = 成功;`WsKey状态失效` = 串不对/已过期
- 验证成功后交给任务自己的 cron,别再手动批量触发其它京东任务(见「京东 cookie 风控教训」)

## 坑

- **京东 App 有证书校验与 SSL Pinning (抓包即断网)**:
  - 现象：一开启 VNET/抓包工具，京东 App 立即失去网络、提示网络异常或无法刷新。
  - 根因：Android 7+ 默认不信任用户 CA 证书，且京东 App 内部启用了 SSL Pinning。当它探测到 TLS 证书非官方直签时会主动断开 TCP/TLS 连接。
  - 对策：不要在陈旧抓包工具（如 VNET）上反复尝试；改用 ProxyPin 针对“仅京东 App”分应用代理；如果仍断网，直接转向**手机或电脑浏览器访问 m.jd.com 抓取网页版 `pt_key` Cookie**，网页不吃客户端 SSL Pinning，更稳定。
- **wskey 长度校验**: 京东标准 `wskey` 为固定 **96 位** 字符。收到用户粘贴的 wskey 时必须先行检查长度，若不足 96 位不可直接写入 env，必须提醒重抓或完整复制整行 Cookie。
- **抓取本身是账号授权操作,有风控风险**:账号刚被风控、或刚触发滑块/人脸验证时别抓,停任务静养几天再动
- wskey 不是永久:被顶号 / 改密码 / 京东 App 手动退出登录 / 风控都会失效(通常能用 3-6 个月),届时重抓;抓包工具的证书过期也要重装
- **不用定期检查/定期抓**:jd_wskey.py 每天跑会先测现有 JD_COOKIE(有效就跳过),wskey 换不出 key 时主动 `ql_send` 推 telegram(「账号: <pin> WsKey疑似失效, 已禁用Cookie」)→ 维护模型是**等推送再抓一次**。用户问"多久抓一次"就按这个答
- 抓包期间**别同时跑青龙的京东任务** —— 同一账号两处并发请求容易再触发风控
