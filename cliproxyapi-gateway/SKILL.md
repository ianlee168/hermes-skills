---
name: cliproxyapi-gateway
description: "Use when deploying or running a CLIProxyAPI gateway."
version: 1.2.0
author: 50.110 bot
license: MIT
platforms: [linux, windows]
tags: [cliproxyapi, cpamc, ai-gateway, docker, unraid, quota, userscript, tampermonkey]
metadata:
  hermes:
    tags: [cliproxyapi, cpamc, ai-gateway, docker, unraid, quota, userscript, tampermonkey]
    triggers: ["CLIProxyAPI", "CPAMC", "配额面板", "8317", "management.html", "管理密钥", "secret-key",
               "cpamc-screenshot", "quota 截图", "codex/claude/gemini 账号池",
               "自建 API 网关", "把 OAuth 账号包成 API"]
    related_skills: [unraid-server-ops, hermes-windows-bash-quirks, hermes-agent]
---

# CLIProxyAPI 网关 + CPAMC 配额面板

## When to Use

- 用户拿来一个 CLIProxyAPI 相关仓库/面板地址问"怎么部署"。
- 要在一台常开的机器上把 OAuth 账号或各家 API key 包成一个 OpenAI/Gemini 兼容端点。
- 第三方客户端（Argos、Cherry Studio、Chatbox 等）问如何接入网关、是否在消耗大池子。
- 面板（`/management.html`）打不开、配额页空白、凭证数为 0、管理接口 401。
- 用户要装 `cpamc-screenshot` 之类给配额面板加截图/分享按钮的用户脚本。

## 是什么 / 先看哪里

- **CLIProxyAPI** 把 Gemini CLI / Codex / Claude Code / Antigravity 这类 OAuth 账号，以及各家的
  普通 API key，包成 OpenAI / Gemini / Claude 兼容端点，做多账号轮换和配额分摊。
- **CPAMC**（Cli-Proxy-API-Management-Center）= 官方管理面板，**内嵌在同一个端口**：
  `http://<host>:8317/management.html`，启动时自动从 GitHub 拉一个单文件 HTML（3 MB 量级）到 `static/`。
- 两种客户端 key 别混：**`access.api-keys`（v8）是客户端拿来调网关的**；**上游提供方的 key 在顶层 `api-keys:`**
  （`gemini:` / `claude:` / `xai:` 等分组，每组一个 `base-url` + `keys:` 列表）。
- 本机已有一套：**50.1 Unraid**，容器 `cli-proxy-api`，appdata `/mnt/user/appdata/cliproxyapi/`。
  入口两个，同一个实例同一把密钥：局域网 `http://192.168.50.1:8317/management.html`、
  公网 `https://cpa.techtreehole.com:16666/management.html`（iStoreOS Lucky 反代 16666，已实测）。
  凭据、实测结论、坑都在 gbrain `tools/cliproxyapi-cpamc-50.1` —— **先 `gbrain get` 那页再动手**，别重建。
- **用户问「管理密钥是什么」= 一次 `gbrain get tools/<app>-<host>`（约 1s）就该答完**。
  别先通读本 skill、别走验证阶梯：slug 已经写在上面这行里，`gbrain search` 反而更慢（6s embed 超时）。
  只有**入口变了**（新域名/新反代端口/新机器）才需要 curl 一次管理接口确认"这个 URL 指向同一实例"——
  那一步是为了避免拿错密钥连错 5 次被 ban 30 分钟，不是走过场。
- 官方文档 `help.router-for.me`（有中文）；config 权威样例是仓库的 `config.example.yaml`。

## 部署（docker 主机；Unraid 惯例）

1. 落点 `/mnt/user/appdata/<app>/`（**合并视图**，不是 `/mnt/cache/...`，否则每日备份抓不到），
   建 `auths/ logs/ plugins/ static/` 子目录。
2. compose：镜像 `eceasy/cli-proxy-api:latest`，端口 `8317:8317`，挂 config.yaml / `auths`→`/root/.cli-proxy-api` /
   `logs` / `plugins`，`restart: unless-stopped`。模板 `templates/compose.yaml`。
3. config.yaml（v8 布局）：`server.host: ""`（监听所有网卡）、`management.allow-remote: true` +
   `management.secret-key`、`access.api-keys`。模板 `templates/config.yaml`。
4. **密钥自己生成、只落到用户能读的文件里**（`secrets.token_urlsafe`，写成 `credentials.txt`），
   聊天与命令文本里不出现值；同时 `gbrain put tools/<app>-<host>` 存一份事实记录。
   **再写一份给人看的 `mgmt-key.txt`**（内容就三行：网关地址、管理密钥、客户端 key 在哪），
   部署完立刻弹到用户屏幕上：`terminal(command='notepad "D:\...\mgmt-key.txt"', background=true)`
   （GUI 程序这样起；别用 `&` —— 工具会拒；也别包 `cmd //c start`，那会开出一个控制台窗口而不是记事本）。
   用户接着一定会问"管理密钥填什么"，**答案是"看那个文件"，不是把值贴进聊天**：他的惯例是凭证不进聊天记录，
   而且面板密钥连错 5 次封 IP，让他复制粘贴比口述安全得多。
5. `docker compose up -d`。**选 7×24 的机器**：Windows 桌面机每天定时关机，"网关半夜断了"就是这么来的。

## 面板入口有两个：局域网端口 + 反代域名（是同一台实例）

- 50.1 这套面板既能在局域网 `http://192.168.50.1:8317/management.html` 打开，也经 iStoreOS 上的 Lucky 反代暴
  露为 `https://cpa.techtreehole.com:16666/management.html`（`techtreehole.com` 的 `16666` 就是 Lucky 的入口，
  bbs 等其它服务也共用它）。**两条路是同一台容器、同一把管理密钥** —— 别因为域名/端口不同就当第二套部署去重建。
- **判断“这个域名是不是同一个实例”最快的证据**：拿管理密钥打对方的 `/v0/management/auth-files`，
  返回 `files[].path = /root/.cli-proxy-api/*.json` 且 `account` 与本地一致 → 同实例；401 才说明密钥或实例不同。
  ⚠️ 失败一次就消耗那 5 次封禁额度，所以**先在本机 8317 确认密钥有效，再去试外部入口**。
- 管理面板一旦经反代暴露到公网，拿到密钥的人就能改账号池 → 回答完顺手提醒一句，并给出 Lucky 的 IP 白名单 /
  关掉公网暴露两个选项，别默认沉默。

## 加 / 换上游 key（config 在远端时）

值经 stdin 传，命令行里只出现 `"$KEY"`：

```bash
docker_host='root@<host>'; app=/mnt/user/appdata/cliproxyapi
ssh "$docker_host" "cp $app/config.yaml $app/config.yaml.bak-\$(date +%Y%m%d-%H%M%S)"
printf '\napi-keys:\n  gemini:\n    - name: gemini-aistudio\n      base-url: "https://generativelanguage.googleapis.com"\n      keys:\n        - api-key: "%s"\n' "$KEY" \
  | ssh "$docker_host" "cat >> $app/config.yaml"
ssh "$docker_host" 'docker restart cli-proxy-api'
```

- 追加前先 `cp` 一份带时间戳的配置（**只增不删**）。
- 别用 `sed -i`/`echo` 把值拼进命令行 —— 它会留在命令文本和历史里。
- 配置是 YAML：**缩进错了服务照样启动**，只是凭证数为 0 —— 下面第 2 步就是抓这个的。

## 上游 base-url：只写裸域名，不带协议路径

- `api-keys.<provider>[].base-url` 必须是**裸 host**：`https://generativelanguage.googleapis.com`。
  程序自己往后拼协议路径（`/v1beta/models/<模型>:generateContent`），写了 `/v1beta` 就成
  `/v1beta/v1beta/...` → 实测**回 404 `model_not_found`**。⚠️ 404 不是 401/403，别顺着"key 无效"排查。
  官方 `config.example.yaml` 的 gemini 组示例同样是裸域名。
- 面板里**两个框都叫「地址」，别混**：
  - 登录页的「自定义连接地址」= **网关自己的入口** `http://<host>:8317`（默认按当前访问地址自动填，通常留空即可）；
  - 「密钥/账户」页新建上游时的「服务地址」= **上游 base-url**（就是上面那条规则，绝不要把 Google 的地址当成网关地址填）。
  用户问"服务地址是 A 还是 B"时，回话前先分清他在哪个页面。

## 改配置前先做无害 A/B（不动在跑的那套）

拿不准一个值怎么填（base-url 带不带路径、模型名、档位）时，**别改生产 config 去试**——
另起一个临时实例：同镜像、别的端口、独立 config，用同一把上游 key 真发一次请求对比：

```bash
ssh "$h" 'mkdir -p /mnt/user/appdata/cliproxyapi-basetest'
scp probe-config.yaml "$h":/mnt/user/appdata/cliproxyapi-basetest/config.yaml
ssh "$h" 'docker run --rm -d --name cpa-basetest -p 8319:8317 \
  -v /mnt/user/appdata/cliproxyapi-basetest/config.yaml:/CLIProxyAPI/config.yaml \
  eceasy/cli-proxy-api:latest'
sleep 7; ssh "$h" 'docker logs cpa-basetest | grep -E "clients|error" | tail -3'   # 凭证加载数不能是 0
ssh "$h" 'docker stop cpa-basetest'                                                # --rm 容器随之自清
```

- 临时实例也要配 `access.api-keys`，否则你连不上自己起的网关；端口别撞 8317。
- **两种写法都真跑一次再回答用户** —— "应该不带路径"不算证据；把实测结果写进回复和 gbrain 页。

## 验证阶梯（每步都要硬证据，别跳）

1. **容器**：`docker ps --filter name=<c> --format "{{.Status}} | {{.Ports}}"`，
   `docker inspect <c> --format 'Restart={{.HostConfig.RestartPolicy.Name}}'`。
2. **凭证真被读进去了**：`docker logs <c> | grep "clients and configuration updated"`
   → 形如 `1 clients (0 auth entries + 1 Gemini API keys + …)`。**看到 0 就是没加载**，回去查 YAML 位置/缩进。
3. **面板**：`curl -s -o <native path> -w "%{http_code} %{size_download}\n" http://<host>:8317/management.html`
   → 200 且**字节数量级对**（≈3 MB；几百字节 = 拉了个错误页）。日志里应有 `management asset updated successfully`。
   从**另一台机器**也打一次，证明局域网可达。
4. **管理 API**：`curl -H "Authorization: Bearer $MGMT" http://<host>:8317/v0/management/auth-files` → 200。
5. **代理鉴权**：不带 key `/v1/models` → 401；带 `access.api-keys` 的值 → 200。
6. **端到端**：`POST /v1/chat/completions` 打一个真实模型，拿到真实回复，才算这台网关能用。

## 消费端接线

`base_url: http://<host>:8317/v1` + `access.api-keys` 的值当 API key，任何 OpenAI 兼容客户端都能接
（Hermes 侧按 custom provider 配，见 `hermes-agent` 的 providers 参考）。

## 配额截图用户脚本（cpamc-screenshot）

它是 **Tampermonkey 用户脚本，不是服务** —— 没有跑起来的 CLIProxyAPI 就没有可截的页面，别本末倒置。

1. 装 Tampermonkey（Chrome/Edge/Firefox 扩展商店），本机 Chrome 已有。
2. 打开 `https://github.com/CookSleep/cpamc-screenshot/raw/main/cpamc-screenshot.user.js` → 点安装。
3. 篡改猴图标 → 「设置 CPAMC 地址」→ 把默认的 `http://localhost:8317` 改成真实地址（如 `http://192.168.50.1:8317`）→
   保存（页面自动刷新）。脚本按 `@match *://*/*` 注入但只在配置的地址上激活。
4. 面板标题右侧出现 `M`（带邮箱）/`Copy`（脱敏）两个按钮即成功。

- **剪贴板只在安全上下文可用（HTTPS 或 localhost）**：内网 `http://192.168.x.x:8317` 会被浏览器拒绝 →
  脚本降级成弹预览窗、要右键手动复制。想一键复制：给面板配 HTTPS 反代，或 `ssh -L 8317:127.0.0.1:8317 root@<host>`
  后用 `http://localhost:8317` 访问。手机端走系统分享 API。
- 脚本 `@require` 了 cdnjs 的 html2canvas，浏览器要能出网。
- 要用浏览器工具替用户点安装，先请他**完全退出 Chrome**，否则 profile 被占用、浏览器会话起不来。

## 远程服务器的 OAuth 登录（浏览器跳 localhost 打不开）

网关在 NAS/远端时，点「启动 OAuth」→ Google 授权同意 → 浏览器跳到 `http://localhost:<port>/oauth-callback?...` **必然打不开**
（回环地址只指向执行浏览器那台机器）。这不是错误配置。回调端口：Codex 1455 / Claude 54545 / Antigravity 51121 /
 xAI 56121 / 备用 11451；容器内转发器起来时日志有 `callback forwarder for <provider> listening on 0.0.0.0:<port>`。

1. **服务端直接完成（最快，已实测）** —— 把完整回调 URL 交给管理 API：
   ```bash
   curl -s -X POST -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
     -d '{"provider":"antigravity","redirect_url":"http://localhost:51121/oauth-callback?state=..&code=.."}' \
     http://<host>:8317/v8/management/oauth/callback      # → {"status":"ok"}
   ```
   成功标志：日志 `Authentication successful! Token saved to /root/.cli-proxy-api/<provider>-<email>.json`，
   且 `auths/` 出现该文件。面板 UI 只有 devin/xai 提供粘贴回调的输入框，antigravity 没有 → 走 API 或下面的隧道。
2. **SSH 隧道（用户自己操作）**：compose 必须**发布对应回调端口**（只发 8317 不够，宿主上必须有人监听），
   再 `ssh -L 51121:127.0.0.1:51121 root@<host>`，然后重新开一次 OAuth，浏览器跳 localhost 时即落到容器。

验证别只看“账号出现在界面”：`/v1/models` 会变多（只挂 AI Studio key ≈14 个；加 Antigravity 账号后 ≈25 个，多出
 `gemini-3.8-flash` / `claude-opus-4-6-thinking` / `gpt-oss-120b-medium` 等），再用**只有该 provider 才能提供的模型**
 打一次请求拿到 200 才算真通。重建容器不丢账户（auths/ 是挂载卷，日志应显示 `N clients (M auth entries + …)`）。

## “面板显示额度满，可我一用就受限” —— 先分辨是哪一套配额

网关一个进程里可能同时挂着两类凭证，**它们的额度互不相干**：

| | AI Studio API key（`api-keys.gemini`） | OAuth 账号（`auths/*.json`，如 Antigravity） |
|---|---|---|
| 额度 | 免费档极小（报错实测 `generate_content_free_tier_requests, limit: 20`） | 5 小时 / 7 天窗口（面板 `#/auth-files` 看到的就是这个） |
| 谁在用 | `base_url=generativelanguage.googleapis.com` + `provider=gemini` = 直连，没走网关 | 走网关 `/v1/chat/completions` |
| 症状 | agent 一轮要 3-10 次调用 → 一两分钟就见底 | 配额窗口没用完就不会受限 |

- **模型名来自哪个凭证是可以看出来的**：网关 `/v1/models` 是**所有凭证目录的并集**。只挂 AI Studio key 时能看到 `gemini-3.8-flash`；
  把它摘掉只留 Antigravity 后同一个位置变成 `gemini-3.8-flash-high`（Antigravity 的目录）——**名字对了但凭证换了的经典陷阱**：
  保留免费档 key 会把 agent 的请求轮流打到只有 20 次额度的那个凭证上，于是“面板额度满着但一直 429”。
- 结论：**agent/日常使用只留 OAuth 账号，把免费档 API key 从池里摘掉**（`sed -i '/^# upstream API keys/,$d' config.yaml` + 备份 + restart），
  然后确认 `docker logs | grep "clients and configuration"` 变成 `1 clients (1 auth entries + 0 Gemini API keys …)`。
- 让 Hermes 吃账号配额：加 custom provider（`api: http://<host>:8317/v1` + `access.api-keys` 的值 + 池里真实存在的 `default_model`），
  `hermes config set providers.<name>.{api,name,api_key,default_model} … --force`，再用 `hermes chat -m <model> --provider <name>` 实测。
- 排错顺序：先看 **Hermes 自己的日志**（`logs/errors.log` 里那条 429 的 `provider=/base_url=/model=`），再数**网关日志里的 429**；
  网关计数为 0 就说明请求压根没走网关，别去查网关配置。
- 注意账号配额是**共享**的：同一 Google 账号在官方客户端（Antigravity 等）里用掉的额度，会和网关请求抢同一对 5h/7d 窗口。

## 后台隧道进程管理（后台任务说明与清理）

为解决远程部署的 2 大问题，会话期间通常会用 `terminal(background=true)` 维持 2 个静默 SSH 隧道：
1. **OAuth 回调隧道**：`ssh -N -L 51121:127.0.0.1:51121 -L 1455:127.0.0.1:1455 -L 54545:127.0.0.1:54545 -L 56121:127.0.0.1:56121 root@<host>`（供浏览器 OAuth 回调到容器）。
2. **面板访问隧道**：`ssh -N -L 8317:127.0.0.1:8317 root@<host>`（供浏览器油猴脚本在 localhost 安全上下文使用剪贴板一键截图）。
- **生命周期**：它们附属于启动它们的终端/Hermes 会话，会话结束或机器重启即断开。
- **查询与识别**：当用户问“后台任务是什么”时，调用 `process_manage(action='list')` 查看当前运行中的后台命令，准确说明每个隧道绑定的端口和用途。
- **如果用户要求关闭或自建常驻**：可直接使用 `process_manage(action='kill', session_id=...)` 结束会话级隧道，并给出用户可手动在终端中保持运行的标准命令。
- **端口冲突预防（核心陷阱）**：如果告诉用户“可以在自己的终端里跑 `ssh -N -L ...`”，**必须先杀掉会话内正在占用该端口的后台隧道**，否则用户在自己终端执行时必然报错 `bind [127.0.0.1]:<port>: Permission denied` / `Could not request local forwarding`，造成困惑。
- **`-N` 参数提示**：用户手动执行 `ssh -N ...` 成功时终端没有任何回显/输出，这是正常现象，必须提前向用户解释光标停顿代表正在运行，并叮嘱窗口不能关闭（只能最小化），避免用户误以为卡死或随手关闭。
- **HTTPS 反代免隧道方案（彻底告别本地隧道）**：
  若在路由器反向代理服务（如 iStoreOS Lucky / Nginx）中将网关的 `http://<host>:8317` 反代为局域网或域名 HTTPS（如 `https://cpa.lan`），浏览器原生赋予剪贴板 API 完整权限（安全上下文）：
  1. 用户在 Tampermonkey 中将 CPAMC 地址直接改为该 `https://...`。
  2. 此时本地既不需要运行 `ssh -N -L 8317:...`，也不需要保留任何 PowerShell 窗口，开机直接访问反代地址即可正常一键截图复制。
  3. OAuth 回调隧道在账号完成认证入池后同样可以直接杀掉释放，无需常驻。

## 方案 1 与方案 2 的区别与权衡（用户选择指导）

当涉及 Gemini/各大模型接入与分流时，经常面临直接配置 API Key 还是通过网关接入账号池的选择：
- **方案 1：官方 API Key (`GEMINI_API_KEY`)**：
  - 直连服务商 API（如 Google AI Studio）。
  - **核心限制**：免费档配额极小（新模型每天可能仅 20 次请求），作为自主 Agent 执行多步骤任务时几轮就会触发 HTTP 429 `RESOURCE_EXHAUSTED`。仅适合低频单次调用或付费项目。
- **方案 2：中央网关 (`cpa` / Antigravity OAuth)**：
  - 流量通过 NAS 上的 CLIProxyAPI 转发，使用官方客户端 OAuth 凭据（Antigravity）。
  - **核心优势**：享受官方桌面/CLI 的长周期配额窗口（如 5 小时 / 7 天动态配额），支持完整模型体系（如 `-high` 级高推理模型），适合作为 Agent 主力通道。
  - **多机协同注意点**：当为主机配置了方案 2 时，其他节点（如东宫 161 姐 VM）若也需要高配额，应在 `config.yaml` 中同样挂载网关 custom provider，而非仅同步 `GEMINI_API_KEY`。

## 多机协同与跨机器同步（50.110 与 50.161 等东宫/西宫协同）

- 当用户在一个会话中更新了 API Key（如 Gemini Key 从 39 位更新到 53 位）或新增了网关渠道，常会询问“东宫（或远程 VM）配置对不对”。
- **必须先查实证再作答**：
  - 通过跨机 SSH（如 `ssh ianlee168@192.168.50.161`）检查目标机器的 `~/.hermes/.env`、`~/.hermes/config.yaml` 及 `auth.json`。
  - 重点核对 Key 长度、前缀与更新时间戳（例如 `AIzaSy...` 与 `AQ.Ab8...`）。
  - 核查 `config.yaml` 是否已添加对应的网关 `custom_providers`（如指向 NAS 的 `cpa` 端点）。
- 若尚未同步，直接向用户汇报两台机器的真实差异，并给出同步具体方案（替换 env key 或接入中央网关）。
- **多 Profile 与常驻网关陷阱（东宫踩坑教训）**：
  - 机器上可能存在多个 Profile（例如东宫同时存在 `default` 和 `webui-hermes` 网页网关）。仅仅在 `providers:` 字典里注册 `cpa` 是不够的，**必须同时更新 `model.default`、`model.provider` 以及 `model.base_url`**，否则重启服务后依然会降级走旧的直连模型（例如仍然显示 `gemini-3.8-flash` 而没有 `-high`）。
  - 配置修改后，**必须重启后台常驻网关服务**（例如 `systemctl --user restart hermes-gateway`），否则内存中的运行实例不会生效。

## 接入标准 API Key 提供商（DeepSeek、OpenAI 兼容端点等）与查看逻辑

- **非 OAuth 提供商分类**：像 DeepSeek、OpenRouter 等基于标准 HTTP API Key 的服务，在 CLIProxyAPI 里归类为 **`api-keys.openai-compatibility`**（或专属分组），而不是 `auths/*.json`（OAuth 认证文件）。
- **配置注入范式**：
  ```yaml
  api-keys:
    openai-compatibility:
      - name: "deepseek"
        base-url: "https://api.deepseek.com/v1"
        keys:
          - api-key: "sk-..."
        models:
          - name: "deepseek-flash"
            alias: "deepseek-flash"
          - name: "deepseek-v4-pro"
            alias: "deepseek-v4-pro"
  ```
  更新后重启网关，检查 `docker logs | grep "clients and configuration"` 是否出现 `N OpenAI-compat`。
- **“在面板哪里查看”的认知差消除**：
  - **不要去 `#/auth-files`**：`#/auth-files` 是 **OAuth 文件专用页**（专门展示 Antigravity、Gemini CLI 等带有 5h/7d 动态额度条的 OAuth 会话）。
  - **去哪里看**：
    1. **可用模型目录**：点击面板顶部的「模型管理」或请求 `/v1/models`，确认 `deepseek-flash` 等已并入模型池。
    2. **配置卡片**：在左侧「配置管理」的 `api-keys -> openai-compatibility` 查看注册的提供商。
    3. **额度限制特性**：第三方 API Key 属于基于 Token 的消耗型扣费，网关面板无法直接获取官网账户的法币/点数余额，仅记录中转请求的请求数与延迟；看余额仍需登录服务商控制台。

## 多模态与多功能模型支持特性（Gemini 与 Antigravity）

- **多模态理解（输入端）**：网关下的 `gemini-3.8-flash-high` 等 Antigravity 渠道模型是**原生多模态理解模型**，支持图像视觉（Vision / 截图 / OCR / 多图）、长 PDF 及音视频上下文理解（实测直接在 `/v1/chat/completions` 传递 Base64 `image_url` 可正常分析识别）。
- **区分“识图”与“画图”**：该渠道支持多模态输入分析，但**不支持图像生成（画图/生图）**。生图需求由带 `-image` 后缀的专属通道承载，且免费档 key 通常不覆盖（易报 429 配额不足）。

## 坑

- **桌面端新窗口「显示 gemini、一问就变 deepseek」= provider 解析不出端点，不是网关坏了**。
  机制：桌面新会话只发裸 `provider='custom'`（不带端点/key），后端的 ladder 只有在
  `model.provider` 是 `custom`/`auto`/loopback 时才肯用 `model.base_url` 兜底 → 否则整条 ladder 落空，
  `_raise_for_credentialless_bare_custom` 抛 AuthError，接着按 `fallback_providers` 掉到 deepseek。
  **`model.provider: cpa`（裸 named 名）正好踩这个洞**：显式请求 `cpa`/`custom:cpa` 都能解析，唯独裸 `custom` 不行。
  诊断顺序：`grep "Primary provider auth failed" logs/errors.log`（会写明 `provider 'custom'`）→
  `python -c "from hermes_cli.runtime_provider import resolve_runtime_provider as r; print(r(requested='custom'))"`
  在 `hermes-agent/` 目录复现，比开浏览器看网关快得多；网关侧再用 `/v1/chat/completions` 直测一次证明上游正常。
  修法（实测四形态全通）：`hermes config set model.provider custom` +
  `hermes config set model.base_url http://<host>:8317/v1`（key 会自动借 `providers.<name>.api_key`，不用另填）；
  `providers.cpa` 条目保留给 MoA/显式 `--provider cpa` 用。config 有文件签名缓存，gateway 进程会热读，
  但**已经跑着的会话不会自愈**——要么新开窗口，要么重启桌面 app。
- **`management.secret-key` 写明文会在启动时被 bcrypt 哈希后写回 config.yaml**（`$2a$…`）。发给管理接口的
  仍然是**明文**；别去"修"文件里那串哈希，也别因为看到哈希就以为明文失效了。
- **`management.allow-remote` 默认 false，只放行 localhost**：从别的机器打管理接口失败时先看这一项，
  跟密钥对不对无关。
- **管理密钥连错 5 次 → 该 IP 封约 30 分钟**，所以核对密钥别凭记忆重打，也别拿猜的值去试公网入口。
- **这 5 次限制是按「程序看到的来源 IP」记账的，经反代进来时那是反代的局域网 IP**：Lucky 转发后的请求在
  `docker logs` 里一律显示网关地址（如 `192.168.50.5`），既查不到真实访客，也意味着**外人瞎试 5 次被锁 30 分钟的是
  你自己、而且能续封**。所以面板一旦暴露公网，这 5 次限制**不能当防线**，要上反代层白名单或后端认证
  （见 `lucky-reverse-proxy`）；同理，别拿日志里的 IP 当「谁在从外网用网关」的证据 —— 公网与局域网直连混在同一份日志里。
- **用户问「这么复杂的密钥不会被破解吧」时的答法**：先用熵给出结论（32 字符 url-safe base64 = 192 bit，
  10¹² 次/秒也要 10³⁷ 年级别），再补一句「真正的风险不是猜，是泄露面」，并**当场把暴露面扫一遍**：
  同一公网端口上还挂了哪些站点、有没有零认证后台/文件服务、这条 URL 是否写在公开仓库里。
  只回「不会」是漏答 —— 用户要的是安全判断，不是安慰。
- **明文已经取不回 config.yaml**：启动后那一行是 bcrypt 哈希，
  `sed -nE 's/^ *(secret-key)[: ]+(.*)$/\2/p' config.yaml` 只会吐出 `$2a$10$…`，哈希不可逆。明文的可靠来源只有两处：
  `gbrain get tools/cliproxyapi-cpamc-50.1` 的「凭据」段、和本机 `mgmt-key.txt` / `credentials.txt`。
- **用户问"管理密钥是什么"的应答流程**（照做，别自由发挥）：① `gbrain get tools/cliproxyapi-cpamc-50.1` 取明文
  （约 1 秒，**不要**先通读本 skill、不要先走验证阶梯 —— 这一条曾被用户当面吐槽"跑了一大圈"）；
  ② **只有入口没被验证过**（新域名/新反代端口/新机器）才 curl 一次 `/v0/management/auth-files` 确认"这个 URL 指向同一实例"，
  同实例同入口已记在 gbrain 里的就跳过（每次错都吃掉一次封禁额度，所以宁可先验证再交付，但别重复验证）；
  ③ 把入口地址补进 `mgmt-key.txt` 并 `notepad` 弹给他（`terminal(..., background=true)`）；
  ④ 回复里说"看那个文件"，**不把值贴进聊天**，只说它和哪次部署是同一把。
- 改了 config.yaml：服务有文件监听会热加载、也可能重写文件；**手工改完 `docker restart` 一次**，
  再回到验证阶梯第 2 步确认新配置真的生效。
- `management.disable-control-panel: true` 会让 `/management.html` 直接 404 —— 别跟"面板坏了"混淆。
- Unraid 上没有 python3：在远端解析 JSON 用 grep/`sed`，或把响应落到本机再解析。
- Windows 侧原生 curl/scp 不翻译 MSYS 路径（`-o /tmp/x`、`/d/...` 会落到别的盘且 curl 仍报成功）→
  一律写 `C:/...`、`D:/...`，或把整条命令放远端执行（详见 `hermes-windows-bash-quirks`）。
  连 `-o /dev/null` 也别用：MSYS 下写 `/dev/null` 会返回 exit 23（write error），而 `-w` 的 http_code 仍正常
  打在 stdout —— 别把这个非零退出码误判成请求失败；要看响应体就落到 `C:/Users/<u>/AppData/Local/hermes/cache/scratch/x.json`。
- **真正的配额来自 OAuth 账号**：在面板里逐个登录（Gemini CLI / Codex / Claude / Antigravity），
  授权文件落在挂载的 `auths/` 目录。这一步**必须用户本人在浏览器点授权**，别承诺代做；
  只挂一把 API key 的网关，面板上的配额信息基本是空的。
- 用户问"怎么部署这个用户脚本"时，先答清**两段式**（先有服务端面板、再有浏览器脚本），
  并当场查一遍现状（`docker ps`、8317 是否有人监听、浏览器里有没有 Tampermonkey），别只复述 README。
- **用户问"某个框填什么"时，先确认是哪个页面再答**：面板同一屏里存在同名不同义的字段（见上面「两个框都叫『地址』」），
  答错会让他的网关连不上、或上游报 404。拿不准就先拉下 `/management.html` grep 字段标签/占位符，别凭印象。
- **容器生命周期命令在本机 Hermes 里要走审批**（`docker restart`/`stop`/`kill` 会弹给用户点同意）→
  把 restart/stop 合并进同一次调用，别一行一个 restart 让用户连点；并在同一句里说清为什么要重启。

## 文件

- `templates/compose.yaml` —— 可直接改的 compose（ports/volumes/restart）。
- `templates/config.yaml` —— v8 最小可用配置（server / management / access.api-keys + 注释掉的 gemini 上游段）。
