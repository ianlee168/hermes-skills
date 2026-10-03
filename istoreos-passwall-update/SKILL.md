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

第二轮实测(26.9.16 → 26.9.27,2026-09-28):资产命名规律、依赖清单与前次完全一致;
路由器**直接** `curl -sL` GitHub release 下载即可(842157/17994 字节,秒级,无需镜像);
这次 `opkg install` 期间 SSH **没断**(全程 exit 0),restart 那条也没断 —— 断线是"可能"不是"必然",
但仍按 nohup 后台 + 重连查 log 走,别在前台等。本次无 `resolve_conffiles` 提示(用户改过的规则文件未被 replan)。

第三轮实测(26.9.27 → 26.10.1,2026-10-01):资产名与 size 规律仍一致(843133/18001 字节,
tag `26.10.1-1`);ipk `Depends` 仍是那 19 项硬依赖,逐项 `opkg list-installed` 复核全部 OK;
`opkg install` 与 `/etc/init.d/passwall restart` 两条命令 SSH **都没断**(restart rc=0),
再证"断线是可能不是必然"。升级前后 `/etc/config/passwall` md5 完全一致(内容未被 replan)、无 `resolve_conffiles`。
验证:sing-box + chinadns-ng 换新 PID 在跑、google/youtube/baidu 均 200、`luci.js=200`。

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

## 批量更新软件包(2026-09-28 实测:62 可更新 → 实升 42)

```sh
# 1. 备份(注意 tar 用 -C /,别用相对路径 —— 会生成几十字节的空包,踩过)
B=/root/backup-$(date +%Y%m%d); mkdir -p $B
opkg list-installed > $B/pkgs-before.txt; uci export > $B/uci-before.txt
tar czf $B/etc-config.tgz -C / etc/config etc/passwd etc/shadow etc/group etc/rc.local etc/init.d etc/sysctl.conf etc/dropbear etc/openwrt_release

# 2. ⚠️ OpenWrt opkg 的 `opkg upgrade` **不接受空参数**(只打印用法),必须显式列包名
P=$(opkg list-upgradable | grep -v "^Multiple" | awk '{print $1}')
opkg upgrade $P
```

**最大的坑:`opkg list-upgradable` 会把被 hold 的包也列出来**,opkg 却拒绝装:
日志里 `Not upgrading package X which is marked hold (flags=0x202)`。不数这行就会把 62 个
当成都升好了(实际只升了 42)。**判断"确实升了多少"只能 `grep -c '^Upgrading' 日志`**,
再用 `opkg list-upgradable` 复核剩余。

iStoreOS 厂商硬锁(hold)的包 = 只能整固件升级,别强拆:
`base-files`(iStoreOS 是 `61~<日期>` 自建版,源里是上游 `1674~...`,119 个文件含 /etc/init.d、
/lib/functions,强升会用上游基础文件覆盖 iStoreOS 定制)、`libopenssl3`/`libopenssl-legacy`/
`libopenssl-conf`/`openssl-util`/`libmbedtls21`、以及 `luci-base`/`luci-compat`/`luci-mod-network`/
`luci-mod-system`/`luci-app-firewall`/`luci-app-upnp`/`luci-i18n-{base,firewall,upnp,dockerman}-zh-cn`。
其余 luci-* 包(26.259 → 26.270,同一 24.10.8 源)升级是安全的,约 2 分钟。

升级后验证:`/etc/init.d/uhttpd restart` → `curl -o /dev/null -w "%{http_code}" http://127.0.0.1/luci-static/resources/luci.js`
应 200(`/cgi-bin/luci` 返 403 是 iStoreOS 登录门,正常)→ passwall 进程在跑 + `google=200`。

### ⚠️ 只升一半会把面板弄挂:前后端 API 错位(2026-09-28 踩)

症状:面板某页报 `RPCError: RPC call to luci/getMountPoints failed with error -32000: Object not found`。
原因:新前端(`luci-mod-status` / `luci-app-package-manager` 26.270 的 JS + ACL 已声明 `getMountPoints`)
调用的方法在 **`luci-base`(旧 26.209,被 hold 没升)** 提供的 `/usr/libexec/rpcd/luci` 里不存在。
**luci 系列跟 luci-base 必须同版**;hold 拦住的包不能只升一半。

诊断命令(定位到底缺哪件):
```sh
grep -c getMountPoints /usr/libexec/rpcd/luci        # 0 = rpcd 对象里缺方法(luci-base 旧)
grep -rln getMountPoints /usr/share/rpcd/acl.d/      # 有 = 新包 ACL/前端已经在用
ubus -v list luci | grep -i mountpoint               # 升完后应看到 "getMountPoints":{}
ubus call luci getMountPoints '{}'                   # 应返回真实挂载表
```

修法:**显式安装能绕过 hold**(只有 `opkg upgrade` 自动升级才被 hold 拦):
```sh
opkg install luci-base luci-compat luci-mod-network luci-mod-system \
  luci-app-firewall luci-app-upnp luci-i18n-{base,firewall,upnp,dockerman}-zh-cn
/etc/init.d/rpcd restart; /etc/init.d/uhttpd restart; rm -f /tmp/luci-indexcache*
```
- 回滚只能靠文件级备份——源里**只有最新版**(`opkg list luci-base` 只列 26.270),
  旧 ipk 不在任何 feed,所以升级前必须 `tar czf … -C / www/luci-static usr/lib/lua/luci \
  usr/libexec/rpcd usr/share/rpcd usr/share/luci`。
- 升 luci-base 会存下 `/etc/config/luci-opkg`(用户的 `/etc/config/luci` 保留,正常)。
- 浏览器还会拿旧缓存的 `rpc.js`,让用户 Ctrl+Shift+R 强刷。

### ⚠️ hold 的真实范围 & 路由器上已存在的每周自动更新脚本

`awk '/^Package:/{p=$2} /^Status:.*hold/{print p}' /usr/lib/opkg/status` → 该机 **604 个包全被 hold**
(kernel、所有 kmod、libc/uci/rpcd/uhttpd/firewall4/dockerd、base-files/openssl/mbedtls…)= **整个固件基线**。
这是 iStoreOS 的策略:固件自带的包只能靠刷固件升级,所以"跳过 hold"方向是对的,但 **luci 家族被劈成两半**:
`luci-base`/`luci-mod-network`/`luci-mod-system`/`luci-compat`/`luci-app-firewall`/`luci-app-upnp` +
几个 `luci-i18n-*-zh-cn` 在固件里(hold),而后装的 `luci-proto-*`/`luci-mod-status`/`luci-app-package-manager`
不在(不 hold)—— feed 一重建就只升一半 → 上面那种面板报错必然复现。

该机 crontab(`crontab -l`)里已有:
```
* * * * * /usr/bin/uhttpd-watchdog.sh                     # 每分钟看 80/443 在不在,不在就重启 uhttpd
30 4 * * 1 /bin/sh /root/opkg-weekly-update.sh            # 每周一自动更新
0 4 * * 1 lua /usr/share/passwall/rule_update.lua ...     # PassWall 规则更新
```
`/root/opkg-weekly-update.sh` 必修的三处(已改并实测):
1. `opkg list-upgradable | grep -v "^Multiple packages"` —— 否则提示行被当包名,每次都白报 `Unknown package Multiple`。
2. **luci 家族用 `opkg install` 显式安装绕过 hold**,其余 hold 包照旧跳过。
3. 升完 **必须 `/etc/init.d/rpcd restart`**(新的 `/usr/libexec/rpcd/luci` 不重启不加载;
   实测重启后 `ubus -v list luci` 才出现 `getMountPoints`),顺带 `uhttpd restart`。
4. 日志防膨胀用 `tail -n 1500 $LOG > $LOG.tmp && cat $LOG.tmp > $LOG`(**不要 rm**)。

**改这种自动化前必须造故障实测**:建 `PATH=/root/faketest/bin:$PATH` 放一个假 `opkg`
(分支打印 `list-upgradable`/`status` 的假输出),用 `LOG=/root/faketest/test.log sh 脚本` 跑一遍,
断言 5 条:Multiple 过滤、固件基础包 SKIP、held luci 走 INSTALL、普通包走 UPGRADE、非 luci hold 包 SKIP。
验证脚本逻辑而不会真动包。

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
- 50.161 访问 50.110 的钥匙:<user-email> 那把公钥已写入(2026-08-12)

## Open-Box 透明代理安装坑(2026-09-08 实测)

- 安装包缺陷:Open-Box(liandu2024/Open-Box)release tar 内文件权限是 600,
  install.sh cp 铺装后 /www/luci-static/.../openbox/status.js、
  /usr/share/luci/menu.d/、/usr/share/rpcd/acl.d/ 全是 600 root:root →
  uhttpd 读不了,Luci 页面报 `HTTP 403 while loading class file .../status.js`。
  症状像没自启,实际服务正常(procd running + node 在跑 + 2026 监听)。
- 修复:chmod 644 三个目标文件 + init.d 755;
  还要 chmod -R a+rX /opt/open-box/openwrt/luci 修源文件,否则 update.sh
  重铺后 403 复发。
- **2026-09-28 复发实例**:`/www/luci-static/resources/view/openbox/status.js` 变回 `-rw-------`
  (mtime = 09-14 装包那次),`luci-app-openbox.json`(menu.d + acl.d 各一份)也是 600,
  `/etc/init.d/openbox`、`openbox-panel` 是 700 → 用户点开 Open-Box 页就报
  `HTTP error 403 while loading class file .../openbox/status.js`。
  修完 `curl -o /dev/null -w "%{http_code}" http://127.0.0.1/luci-static/resources/view/openbox/status.js` 应 200。
- **一次扫干净所有权限坑**(比背文件清单靠谱):
  `find /www/luci-static /usr/share/luci /usr/share/rpcd /etc/init.d -type f ! -perm -044`
  (输出为空才算干净;修完再跑一遍复核)。
- 两个服务的正确状态:`openbox`(内核/透明代理侧)**inactive + 未 enable 是对的**(该机透明代理归 passwall);
  `openbox-panel`(node 面板,0.0.0.0:2026)应 running + enabled。
- 检查端口用 netstat -tlnp,BusyBox 无 ss 命令(ss 误报 NO_LISTEN)。
- 安装/升级前:该机 passwall 常驻启用,Open-Box 启内核前必须停 passwall,双透明代理会抢防火墙/DNS。
- 面板 http://192.168.50.5:2026,首次访问强制设管理密码;LuCI 兜底页在 服务→Open-Box。
- SSH 直连 GitHub raw 可达(301 正常),78MB 资产下载建议 --mirror(ghfast.top 已验证可用)。

## 环境备忘(50.110 实测)

- iStoreOS: 192.168.50.5, dropbear 端口 64891, root, 本机公钥已授权
- 固件: iStoreOS 24.10.8 (OpenWrt 24.10), x86_64, 内核 6.6.144, 商店 = istorex
- opkg 源: 官方 cernet 镜像 + `istore_compat https://istore.istoreos.com/repo/all/compat`(空壳 dummy 包,别指望它有 passwall)
- ttyd 7681 无鉴权开放是安全隐患;用完提醒用户关掉或加鉴权
