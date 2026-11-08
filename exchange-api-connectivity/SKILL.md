---
name: exchange-api-connectivity
description: Use when exchange API keys fail in 3commas or bots.
version: 1.0.0
author: 110妹@50.110
license: MIT
platforms: [windows]
tags: [binance, 3commas, api-keys, ip-whitelist, trading-bots, cloudflare]
metadata:
  hermes:
    tags: [binance, 3commas, api-keys, ip-whitelist, trading-bots, cloudflare]
    triggers: ["Invalid API Key", "Authentication Error", "3commas", "binance api",
               "连接交易所", "添加交易所", "API密钥", "IP白名单", "trade.3commas.io",
               "交易机器人连不上", "币安 api 权限", "spot futures coin-m"]
---

# 交易所 API 连接（3commas / 机器人平台）

## When to Use

- 平台（3commas / 同类机器人平台）连交易所报 `Authentication Error. Invalid API Key.`，尤其是 Spot / COIN-M / USDT-M 三个市场同时报。
- 要往 3commas 里「添加交易所」并手动贴 API key（而不是 Fast Connect）。
- 币安提示某把 key 缺少 IP 限制、或需要重做白名单。
- 用户说「把币安和 3commas 连上」「帮我看看这个 key 为什么不行」。

不适用：交易所自身的 API 报错码排查（如 -1003 限频、下单参数错）—— 那是交易逻辑层，不是连接层。

平台显示的报错是它自己翻译过的，**不是交易所的错误码**。同一句
`Authentication Error. Invalid API Key.` 可能来自：IP 不在白名单、secret 失配、
权限缺项、key 被删。所以永远先读两侧事实再下结论，别按报错字面去修。

## 硬规矩

- **IP 清单每次当场取，不背、不复用。** 平台换机房就变；旧清单留在脑里 = 明天再挂一次。
- **密钥原文只在创建那一刻显示一次。** 拿不到就新建一把，别花时间“找回”。
- **三个市场一起报同一句错 = key 级问题**（IP / secret / key 不存在），不是某个市场单独配错。
- **改币安 API 设置要强验证**（通行密钥 / 人脸 / App 扫码），生物特征和扫码只能用户做：一次说清要他在屏幕那个窗口做哪一步，然后一次到位，别反复空转。
- **判断成功只认结果面**：key 列表多了一条、连接行变「活跃」，而不是“弹窗消失了”“我点了连接”。
- **不删旧东西收尾**：旧 key / 旧连接一律不删（删除要用户同意），新建共存就行。

## 1. 先分清缺口在哪一侧

- 平台「我的交易所」列表里**有没有**这条连接？只有一条 DEMO 说明那些报错是「添加/连接」抽屉里的市场测试结果 —— 连接一次都没建起来，不是既有连接坏了。
- 交易所侧读 key 列表、权限勾选、IP 白名单（见 §2）。

## 2. 交易所侧取证（Binance）

- 页面：`https://www.binance.com/zh-CN/my/settings/api-management`。卡片**默认折叠**，只看到名字和 HMAC 标签；点「编辑权限」才展开权限勾选与 IP 段。
- 交易类连接要齐：`允许读取` + `启用现货、杠杆和股票交易` + `允许合约`。缺合约时 futures 一定失败而 spot 可能照常 —— 但三个一起报错说明问题在更上层。
- **读勾选状态要读 `aria-checked`**（`document.querySelectorAll('[role=checkbox]')`），别从 `innerText` 里数标签：标签一直在，状态不在文本里。
- IP 模式选「只访问受信任的 IP(推荐)」；币安明说非受限 + 有交易权限的 key **会被删除**，别图省事选“无限制”。

## 3. 平台侧取证（3commas v2）

- 我的交易所 = `https://trade.3commas.io/zh/trader/my-exchanges`（`/settings/exchanges`、`/my/exchanges` 都 404 了）。
- **「添加交易所 → 选交易所」抽屉里就是该平台当前的出口 IP 全量清单**（币安当前 14 个，右侧带复制图标）。这是唯一权威来源，当场复制进交易所的 IP 白名单。
- 抽屉表单：`#myExchanges_accountName` / `#myExchanges_api` / `#myExchanges_apiSecret`，另有 `仓位模式` Auto/One way/Hedge（默认 Auto 即可）。

## 4. 定位结论（按概率排序）

1. **白名单不完整。** 币安对非白名单 IP 返回 -2015（`Invalid API-key, IP, or permissions for action`），平台把它译成上面那句。典型指纹：白名单里只有平台清单的一个子集（例如 14 个里只有 4 个，剩下 10 个 IP 的请求全被拒）。先按这个假设推进：把清单补全。
2. **secret 失配 / key 已被删或重建。** 表现与 1 完全一样。判别：白名单已补全仍报同一句 → 走 §5 新建 key。
3. **权限缺项**（没勾合约 → 只有 futures 报错；没勾现货 → 只有 spot 报错）。

## 5. 新建 key（币安，secret 不可逆时）

- `创建 API` → **系统生成（HMAC）** → 命名 → 下一步。3commas 只吃 HMAC，Ed25519/RSA 不行。
- 创建表单只收名字；**权限和 IP 要建完再「编辑权限」**。
- **「允许合约」「现货」灰的勾不上 = 页面顶部「默认安全控制措施」被勾选。** 先取消那一勾（会触发一次强验证），之后「编辑权限」里的复选框才从 `aria-disabled=true` 变成可点。这是最容易被误判成「币安不让改权限」的坑。
- 编辑面板里 IP 是**一个**输入框，placeholder 含「输入多个IP地址时，请使用空格隔开」，把 14 个 IP 用空格连成一行填进去，再点该段的「确认」提交成 chips（输入框会被清空，属正常）。
- 保存后核验 IP 条数不能看卡片默认显示（只显示前 4 个 + 「更多」）：点「更多」再把卡片 innerText 里的 IP 正则去重计数，等于 14 才算成功。
- **强验证弹窗打开时整个权限表单是 `aria-disabled=true`。** 别把这个状态当成功能限制；弹窗一关就恢复。
- 扫/通行密钥验证成功后，同一次会话内的后续改动往往免二次验证（有宽限期）。
- **扫码必须在币安 App 里点确认。** 只扫不点，弹窗会静默关闭、key 没建出来 —— 回来先查 key 列表，别以为完成。

## 6. 把 key/secret 搬进平台，全程不进聊天

- 在币安卡片的 `密钥:` 行点「显示」后，`li.innerText` 里就是 key 和 secret 明文。**注意：把整个 innerText 打印出来等于把 secret 贴进对话记录**——只取长度/前缀来校验，值落到 `D:\hermes-test\.3c_key.json` 之类本地文件。
- 再在同一个浏览器里用原生 setter + `input`/`change` 事件填 `#myExchanges_api` / `#myExchanges_apiSecret`（`#myExchanges_accountName` 随便起个名如 `Binance-Main`），点抽屉底部「连接」。
- 平台登录要口令时走 `browser_vault action=save_login`（掩码输入，秘书不接触密码），identifier 自己填 `input[name=_username]` 后提交。

## 7. 访问前置：headless 过不了 Cloudflare

`trade.3commas.io` 登录页挂 Cloudflare Turnstile。Hermes 默认的 headless Chrome 会一直停在“正在进行安全验证”；**可视化 Chrome 直接过**。做法：

1. 完全退出用户自己的 Chrome（否则 `use_real_profile` 会 fallback 成全新浏览器，登录态全丢，且它还是 headless）。`Stop-Process -Name chrome -Force` 后核对计数为 0（`cmd //c taskkill` 在这里会静默空转）。
2. 复制最小 profile 到 D 盘：`Local State`、`Default/Network/Cookies`、`Default/Preferences` → `D:\hermes-test\cprof`（Cookies 同用户 DPAPI 可解，复制即可复用登录态）。
3. 起可视化实例：`chrome.exe --remote-debugging-port=9222 --user-data-dir=D:\hermes-test\cprof --no-first-run --no-default-browser-check`。
4. `hermes config set browser.cdp_url http://127.0.0.1:9222` → 之后 `browser_exec` 直接驱动这个可见浏览器（`navigator.webdriver` 为 false）。
5. 收尾把 `browser.cdp_url` 清回空，并问用户要不要删 `D:\hermes-test\cprof`。

## 8. 收尾验证

- 连接行状态「活跃」+ 余额显示出来才算成；`连接` 按下去只是发了个请求。
- **整页跳转刷新（goto_url 重载），再读一次状态**：既确认服务端真存了 key，也避免缓存的“失败”假象。
- 成功的指纹：`活跃` + 现货余额有数字 + `合约 (Coin-M)` / `合约 (USDT-M)` 显示「账户没有资产！」（说明认证通过、只是没钱），而不是 `Authentication Error`。
- 成功后把 key/secret 落到 gbrain `credentials/` 页（用户既定偏好），本地临时明文文件清空。
- 报告里说清：改了哪把 key、白名单多少 IP、哪些市场通了、哪一步是用户亲手做的（扫码/生物识别）。旧 key 旧连接一律不删。

## 字段/选择器与报错映射速查

`references/binance-3commas.md`
