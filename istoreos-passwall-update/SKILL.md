---
name: istoreos-passwall-update
description: 'PassWall update on iStoreOS: direct opkg, no ipk->run.'
version: 1.0.0
author: 50.110 bot
license: MIT
platforms: [windows, linux]
tags: [istoreos, openwrt, passwall, opkg, ttyd, router, websocket]
metadata:
  hermes:
    tags: [istoreos, openwrt, passwall, opkg]
    triggers: ["passwall 升级", "ipk 转 run", "istore run 格式", "passwall 26.8", "iStoreOS 更新插件", "ttyd 无法输出", "ttyd websocket 协议", "ttyd 没有输出"]
---

# iStoreOS PassWall 升级 & ipk/run 问题

## When to Use

- 用户问 PassWall 怎么升级 / 提示"暂不支持自动更新" / 看到版本号 `26.x.y`
- 用户问 ipk 能不能转成 iStore 的 .run 格式(答案:不需要,本地安装原生支持 ipk)
- 需要通过免密网页终端(ttyd)操作路由器,或 ttyd 连上但收不到输出
- 需要在 Windows 侧无 sshpass 时做密码 SSH 登录

## 核心事实(先记住)

1. **ipk 不需要转 run**:iStoreX/iStore「本地安装」原生支持 .ipk。源码证据:`linkease/istore` 仓库 `luci/luci-app-store/root/bin/is-opkg` 的 `dotrun()` 函数:文件名以 `.run` 结尾 → 直接执行;其他 → `opkg install "$path"`(apk 系用 `apk add --allow-untrusted`)。所以商店上传 ipk 即可,转 .run 纯属多余。
2. **PassWall 上游仓库已迁移**:`xiaorouji/openwrt-passwall` → **`Openwrt-Passwall/openwrt-passwall`**(旧地址 GitHub API 404)。版本号现在是日期式 `YY.M.P`(如 26.8.12 = 2026-08-12 发布)。
3. **Release 资产按 OpenWrt 版本分类**:`22.03-` / `23.05-24.10` / `25.12+`(.apk 格式)。iStoreOS 24.10 选 `23.05-24.10_luci-app-passwall_<ver>_all.ipk`。
4. **PassWall 内置版本检查**读取 `Openwrt-Passwall/openwrt-passwall-packages` release 的 api-cache JSON(见路由器 `/usr/lib/lua/luci/passwall/com.lua`),提示"暂不支持自动更新"是正常的——它只查版本,不给 ipk。

## 升级流程(实测 26.7.1 → 26.8.12,2026-08-12)

```bash
# 1. 查最新版本和资产(GitHub API)
curl -s "https://api.github.com/repos/Openwrt-Passwall/openwrt-passwall/releases?per_page=3" | jq '.[].tag_name'

# 2. 下载匹配固件的 ipk(以 iStoreOS 24.10 / x86_64 为例)
curl -sL -o /tmp/luci-app-passwall.ipk \
  "https://github.com/Openwrt-Passwall/openwrt-passwall/releases/download/<TAG>/23.05-24.10_luci-app-passwall_<VER>-r1_all.ipk"
curl -sL -o /tmp/luci-i18n-passwall-zh-cn.ipk \
  "https://github.com/Openwrt-Passwall/openwrt-passwall/releases/download/<TAG>/23.05-24.10_luci-i18n-passwall-zh-cn_<VER>_all.ipk"

# 3. 检查依赖(ipk 是 tar.gz:tar xzf 后 tar xzf control.tar.gz,cat control 看 Depends)
# 26.8.12 硬依赖: chinadns-ng, dnsmasq-full, ip-full, luci-compat, luci-lua-runtime,
#   microsocks, dns2socks, resolveip, tcping, lyaml, coreutils-* — 不依赖 xray-core 版本
# 缺的用 opkg install 补(microsocks 在官方 packages 源)

# 4. 备份配置(升级不动配置,但备份防手滑)
cp /etc/config/passwall /etc/config/passwall.bak-$(date +%Y%m%d)

# 5. 上传并安装(scp 到 /tmp 后)
opkg install /tmp/luci-app-passwall.ipk /tmp/luci-i18n-passwall-zh-cn.ipk
# "Collected errors: resolve_conffiles ... 新文件另存为 -opkg" 是正常提示
# (用户改过的规则文件被保留,新版另存),不是安装失败

# 6. 重启验证
/etc/init.d/passwall restart
opkg list-installed | grep passwall        # 应显示 26.8.12-r1
pgrep -af "sing-box|xray|chinadns"        # 核心进程在跑
```

回滚:从 GitHub release 的旧 tag(如 `26.7.1-1`)下载同款 ipk 重装。

## SSH 会话会断两次(26.9.9→26.9.16 实测 2026-09-18)

升级全程 SSH 会断线(exit 255)两次,这是正常现象不是失败:

1. **`opkg install` 期间**断一次 —— 所以安装命令必须 `nohup ... &` 后台跑,再重连查 `/tmp/pw-install.log`,
   别在前台等(前台等会拿到空输出 + 255,误以为失败)。
2. **`/etc/init.d/passwall restart` 期间**断一次 —— restart 会重置 NAT/防火墙表,把已建立的 SSH 连接打断。
   因此**不要把 restart 和验证写在同一条 SSH 命令里**(验证部分永远拿不到执行),分两条:
   先 restart(断就断),再重连 `sleep 20` 后做验证。

```sh
# 后台装 + 轮询(用 -x 精确匹配,pgrep -f 会匹配到自己那条 sh -c 永不退出)
nohup sh -c "opkg install /tmp/luci-app-passwall.ipk /tmp/luci-i18n-passwall-zh-cn.ipk > /tmp/pw-install.log 2>&1" >/dev/null 2>&1 &
i=0; while [ $i -lt 25 ]; do pgrep -x opkg >/dev/null 2>&1 || break; sleep 10; i=$((i+1)); done
tail -12 /tmp/pw-install.log
```

- 资产名规律两次一致:`23.05-24.10_luci-app-passwall_<VER>-r1_all.ipk`(app 带 `-r1`)、
  `23.05-24.10_luci-i18n-passwall-zh-cn_<VER>_all.ipk`(i18n 不带),tag = `<VER>-1`。
- `resolve_conffiles ... 新文件另存为 -opkg`(direct_host / proxy_host)是正常提示:用户改过的规则保留,
  新版存为 `*-opkg`。不要拿新版去覆盖用户的(用户的域名清单才是他要的)。
- 验证三件套:`opkg list-installed | grep passwall` + `/etc/init.d/passwall enabled` +
  `curl -o /dev/null -w "%{http_code}" https://www.google.com`(经代理应 200)。

## ttyd 1.7.x WebSocket 协议(免密网页终端)

坑:裸 WS 连上(101)但**永远收不到输出** —— 因为缺子协议。

```python
import asyncio, websockets, json
async def main():
    async with websockets.connect("ws://HOST:7681/ws",
                                  subprotocols=["tty"],      # 关键!缺了这个零输出
                                  ping_interval=None) as ws:
        await ws.send("1" + json.dumps({"cols": 120, "rows": 30}))  # resize: "1"+json
        await ws.send("0echo hi\n")                                  # 输入: "0"+data
        out = await ws.recv()
asyncio.run(main())
```

- 客户端→服务端:文本帧 `"0"+输入数据`;resize 帧 `"1"+JSON`
- 子协议必须带 `["tty"]`,否则连接存活、ping 正常,但终端不产生任何输出
- 1.7.3 服务端指纹:`server: ttyd/1.7.3 (libwebsockets/4.3.3-unknown)`;页面 664KB(内联 xterm.js)
- 注意:某些 ttyd 实例即使协议正确也可能无输出(如被 LuCI 鉴权改造过)——遇到就换 SSH 路径

## Windows 侧 SSH 免密/密码技巧

- 密码登录无 sshpass 时:写 `askpass.sh`(`#!/bin/sh\necho '密码'`),然后
  `SSH_ASKPASS=/c/Users/<user>/askpass.sh SSH_ASKPASS_REQUIRE=force DISPLAY=:0 ssh -p PORT root@HOST 'cmd'`
- 公钥免密:本机 `~/.ssh/id_ed25519` 公钥追加到路由器 `/etc/dropbear/authorized_keys`
  (dropbear 无 AuthorizedKeysFile 配置时默认回退 `$HOME/.ssh/authorized_keys`;
  OpenWrt LuCI 管理权页面写入的就是这个文件;别在 `/root/.ssh/` 里找,host key 在 /etc/dropbear/)
- 传文件:`SSH_ASKPASS=... scp -P PORT file root@HOST:/tmp/`
- 临时 askpass 脚本用完即删(含密码明文),删除用 Python os.remove 或 cmd del,注意 MSYS 引号坑

## Windows OpenSSH Server 坑(50.110 实测 2026-08-12)

- 安装:winget 装 Microsoft.OpenSSH 失败(exit -1978335212)时,直接下载
  PowerShell/Win32-OpenSSH release 的 MSI(curl -o 用 `C:/...` 原生路径,`/c/...` 会被 Windows curl 吃掉),
  msiexec /i xxx.msi /qn 即可
- **管理员组成员用户的钥匙必须放 `C:\ProgramData\ssh\administrators_authorized_keys`**,
  不是 `~/.ssh/authorized_keys`!sshd_config 的 `Match Group administrators` 分支强制换文件;
  文件 ACL 必须 `/inheritance:r` + 仅 SYSTEM/Administrators 有权,否则 preauth 直接拒绝
- 排查:改 sshd_config `LogLevel VERBOSE` + 重启,事件查看器 OpenSSH/Operational 给确切原因
  ("Failed publickey ... " / "no hostkeys")
- 防火墙只放行局域网:`New-NetFirewallRule -RemoteAddress 192.168.50.0/24`
- 50.161(161姐/东宫姐姐)访问 50.110 的钥匙:<USER_EMAIL> 那把公钥已写入(2026-08-12)

## Open-Box 透明代理安装坑(2026-09-08 实测)

- 安装包缺陷:Open-Box(liandu2024/Open-Box)release tar 内文件权限是 600,
  install.sh cp 铺装后 /www/luci-static/.../openbox/status.js、
  /usr/share/luci/menu.d/、/usr/share/rpcd/acl.d/ 全是 600 root:root →
  uhttpd 读不了,Luci 页面报 `HTTP 403 while loading class file .../status.js`。
  症状像没自启,实际服务正常(procd running + node 在跑 + 2026 监听)。
- 修复:chmod 644 三个目标文件 + init.d 755;
  还要 chmod -R a+rX /opt/open-box/openwrt/luci 修源文件,否则 update.sh
  重铺后 403 复发。
- 检查端口用 netstat -tlnp,BusyBox 无 ss 命令(ss 误报 NO_LISTEN)。
- 安装/升级前:该机 passwall 常驻启用,Open-Box 启内核前必须停 passwall,双透明代理会抢防火墙/DNS。
- 面板 http://192.168.50.5:2026,首次访问强制设管理密码;LuCI 兜底页在 服务→Open-Box。
- SSH 直连 GitHub raw 可达(301 正常),78MB 资产下载建议 --mirror(ghfast.top 已验证可用)。

## 环境备忘(50.110 实测)

- iStoreOS: 192.168.50.5, dropbear 端口 64891, root, 本机公钥已授权
- 固件: iStoreOS 24.10.8 (OpenWrt 24.10), x86_64, 内核 6.6.144, 商店 = istorex
- opkg 源: 官方 cernet 镜像 + `istore_compat https://istore.istoreos.com/repo/all/compat`(空壳 dummy 包,别指望它有 passwall)
- ttyd 7681 无鉴权开放是安全隐患;用完提醒用户关掉或加鉴权
