# Binance ⇄ 3commas 速查

## 账号与入口

- 币安与 3commas 用同一个邮箱账号；3commas 口令走 vault 掩码输入，不进聊天。
- 3commas 控制台：`https://trade.3commas.io/zh/trader/...`；旧路径 `/settings/exchanges`、`/my/exchanges` 已 404。
- 3commas 的 Google SSO 也要 Google 密码（profile 里没有 Google 会话），不是省事路径；邮箱+密码更快。

## 3commas v2 关键 DOM

| 用途 | 选择器 / 位置 |
|---|---|
| 登录邮箱 / 密码 | `input[name=_username]` / `input[name=_password]`（另有 `_csrf_token`） |
| 我的交易所 | `/zh/trader/my-exchanges`；表头 交易所/名称/API/USD 总价值/已启用/操作 |
| 添加交易所 | 内文为 `添加交易所` 的 `button`（页面上有时匹配到两个，取第一个） |
| 平台出口 IP 清单 | 抽屉正文 `安全连接密钥 完整指南` 下方那段 IP 列表（币安当前 14 个）+ 复制图标 |
| 连接表单 | `#myExchanges_accountName`、`#myExchanges_api`、`#myExchanges_apiSecret`、仓位模式 Auto/One way/Hedge |

抽屉内容常常不在主 `document.body.innerText` 里（在带 `[class*=modal]` 的容器里）；取文本用
`[...document.querySelectorAll('[class*=modal],[class*=drawer]')].map(x=>x.innerText)` 过滤长度。
卡片表头可以 `click()` 展开，但移动宽度下详情会被折叠隐藏 —— 想看全就先
`cdp('Emulation.setDeviceMetricsOverride', width=1600, height=1200, ...)` 再重载。

## 币安 API 管理关键 DOM

- URL：`/zh-CN/my/settings/api-management`。
- 卡片按钮：桌面宽度下叫 `编辑权限`，窄屏折叠成 `编辑`；`编辑` 只是改标签名，**不是**改权限。
- 权限勾选：`[role=checkbox]` + `aria-checked`；标签文本：`允许读取`、`启用现货、杠杆和股票交易`、`允许合约`、`允许万向划转`、`允许提现`、`允许交易币对白名单`。
- IP 模式：`[role=radio]`（`无限制(缺乏安全)` / `只访问受信任的IP(推荐)`）+ 已存 IP 段（超过 4 个折叠在 `更多` 里）。
- 新建流程：`创建 API` → `选择API密钥类型`（`系统生成` / `自行生成`）→ `下一步` → `input[name=apiName]` → `下一步` → 安全验证。
- IP 输入框：`input[name="tradeIps[i].ip"]`，i=0..13。
- 安全验证弹窗不在主 DOM（用 `cdp('Accessibility.getFullAXTree')` 看文案）：可能是「通行密钥（Windows Hello）」、人脸识别、或「币安 App 扫码」。扫码要 App 里点确认，否则弹窗静默关闭且 key 未创建。

## 报错 → 原因映射

| 平台显示 | 实际含义 | 先查什么 |
|---|---|---|
| `Authentication Error. Invalid API Key.`（Spot/COIN-M/USDT-M 同时） | 币安 -2015：key/secret/IP/权限任一不过 | IP 白名单是否覆盖平台全量清单 → secret 是否失配 → key 是否还在 |
| 只有 Futures 报错 | key 未勾 `允许合约`，或 futures 未开通 | 权限勾选 |
| 只有 Spot 报错 | 未勾现货/杠杆 | 权限勾选 |
| 连接后很快变成异常/失效 | 币安会清理“非受限 IP + 交易权限”的 key | 是否选了「只访问受信任的IP」 |
| 点连接弹 “API key already exists” | 同一把 key 已经绑在另一条连接 | 先删那条连接或换 key |

## 别做的事

- 不要把某次抓到的 IP 列表写进 skill 或记忆当常量 —— 平台换机房就失效，每次重新从抽屉取。
- 不要在没拿到 secret 的情况下去“试”旧 key：失败与否都说明不了问题，只会浪费时间。
- 不要删旧 key / 旧连接来“干净重来”：删除要用户同意，且可能连带影响已绑定的机器人。
- profile 副本里的 Cookies 能直接用，但别把它当长期登录手段：3commas 会话过期后仍然要重新走登录（vault 掩码输入）。
