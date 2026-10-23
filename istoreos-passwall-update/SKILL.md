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
    triggers: ["passwall 升级", "ipk 转 run", "istore run 格式", "passwall 26.8", "iStoreOS 更新插件", "ttyd 无法输出", "ttyd websocket 协议", "ttyd 没有输出", "passwall tcp未运行", "脚本已经在运行，不重复运行", "passwall 启动死锁"]
---

# iStoreOS PassWall 升级 & 排错运维

## When to Use

- 用户问 PassWall 怎么升级 / 提示"暂不支持自动更新" / 看到版本号 `26.x.y`
- 用户反馈 PassWall 面板提示「TCP 未运行」或日志死循环「脚本已经在运行，不重复运行，退出」
- 透明代理断网修复后，手机端（Google Play 商店等）依然提示「请重试」
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

第四轮实测(26.10.1 → 26.10.4,2026-10-05):流程与前三轮完全一致(846995/18016 字节,tag `26.10.4-1`,
依赖齐、备份 md5 与升级后一致、SSH 未断、三件套全绿)。
- 上游发版很密(26.9.27 → 26.10.1 → 26.10.3 → 26.10.4,几乎一天一版):**每次都先查 GitHub API 的确切 tag/资产名再下载**,
  别把上一次的版本号当结论照护。
- 新观察:`opkg install` 日志会出现 `Removing obsolete file /usr/share/passwall/helper_smartdns.sh.` ——
  这是新包 control 里声明的 obsolete 清理,**正常**,不是它删了用户的东西。

第五轮实测(26.275 → 26.278,2026-10-10):64 行 - 4 行 `Multiple` = 60 真包,与 hold 交集 **10 个** → 实升 **50**,
依然只认真 `grep -c "^Upgrading"` 日志。
- 本轮的 hold∩可更新 多出 **ddns-scripts 家族**(`ddns-scripts`/`-services`/`-cloudflare`/`-dnspod`,
  2.8.2-r66 → r68,固件里是 hold)→ 又一处“hold 集合会变”的实例:同一台机器三次查询分别是 6 / 6 / 10 个。
- busybox **没有 `comm`**(踩:写 `comm -12 <(...) <(...)` 会报 `ash: comm: not found`,还会把计数弄成假 0),
  求交集/差集统一用 `awk "NR==FNR{h[\$1];next} (\$1 in h)" hold.txt list.txt`。

第六轮实测(26.283 → 26.286,2026-10-16):形状与第四/五轮完全一致(64 行 - 4 `Multiple` = 60 真包,
hold∩可更新 = 10 个,实升 **50**,唯一 Collected error 仍是 `/etc/config/luci` → `luci-opkg`)。
- **有价值的旁证**:上上次手动升到 26.278 后,本轮的起点已是 26.283 —— 中间那一跳是**每周一 04:30 的
  `/root/opkg-weekly-update.sh` 自己做掉的**(2026-10-12),面板没有任何报错 ⇒ 09-28 那次脚本加固
  (过滤 `Multiple`、luci 家族绕过 hold、升完 `rpcd`+`uhttpd` restart)在**无人值守**下已验证有效。
- 手动升级前先 `date` + `opkg list-installed | grep luci-base`:看到版本比上次记的高一档,就是周脚本跑过了,不是异常。

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

## 开机后 PassWall 不启动，日志只有“脚本已经在运行，不重复运行，退出”(2026-10-23 实测)

症状：重启后 TCP 代理全断（`google=000`、`baidu=200` 直连正常），面板点启动也没用；
`/var/log/passwall.log` 只有：
```
10:20:53: 执行启动延时 60 秒后再启动!
10:22:32: 脚本已经在运行，不重复运行，退出.
```
进程里 `{S99passwall} /bin/sh /etc/rc.common /etc/rc.d/S99passwall boot` 一直挂着，
`/proc/<pid>/fd/9 -> /tmp/lock/passwall.lock`（**它自己掮着 flock**），wchan=do_wait；
`/tmp/lock/passwall_ready.lock` 不存在 = 本次开机 boot 没走完。

机制：`/etc/init.d/passwall` 的 `boot()` 把 `boot_func` 丢后台：读 `uci get passwall.@global_delay[0].start_delay`
（该机 60）→ `sleep` → `restart boot`；`restart` 先 `set_lock`（flock fd9）再跑 `app.sh stop/start`。
这条链一旦卡住（开机 DNS/网络未就绪、dnsmasq、订阅锁），**锁永不释放而且脚本没有任何超时**，
之后每次 `start` 只打一句“已经在运行”就 **return 0** —— 静默失败，看上去像“服务自己不在”。

现场处置（30 秒）：
```sh
# 1) 找出掮锁进程并杀（杀进程 = 释放 flock）
for d in /proc/[0-9]*; do for f in $d/fd/*; do [ "$(readlink $f)" = /tmp/lock/passwall.lock ] && echo ${d#/proc/}; done; done
kill -9 <pid>
# 2) 正常启动 + 验证
/etc/init.d/passwall start; sleep 15; pidof sing-box
curl -s -o /dev/null -w "google=%{http_code}\n" --max-time 10 https://www.google.com
```

长效防复发（已在该机落地）：`/root/passwall-watchdog.sh` + `*/5 * * * * /bin/sh /root/passwall-watchdog.sh`
- `pidof sing-box` 有 → 直接退出（不产生日志噪音）
- 否则看 `/tmp/etc/passwall/acl/default/global.json` 的 mtime：<180s = 正在启动，等下一轮
- >180s 或文件不存在（刚开机 /tmp 被清）→ 杀掉持有 `/tmp/lock/passwall.lock` 的进程 → `passwall start`
  → 20s 后复查，结果写 `/tmp/passwall-watchdog.log`（超 800 行原地截断）

造故障实测：`kill -9 $(pidof sing-box)` + `touch -t` 把 global.json 改老 → 跑脚本 → **29 秒后 `repaired OK`**，
google/youtube/baidu 全 200。

两个坑：
- **别用 `pgrep -f "passwall/bin/sing-box"` 判活**：agent 通过一条 ssh 命令跑脚本时，整条 ssh 命令的 cmdline
  里就含这个字符串，`pgrep -f` 会匹配到自己 → 脚本误判“服务还在”什么都不做。用 `pidof sing-box`（按进程名）。
- 脚本下发不能带 CRLF：Windows 上 python `write_text` 默认把 `\n` 写成 `\r\n`，ash 报
  `syntax error: unexpected word (expecting "do")`。用 `open(..., newline="\n")`，或写完后 `sed -i 's/\r$//'`。

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

第三轮实测(2026-10-03,26.270 → **26.275**,同一天还升了 passwall 26.10.1):
- `opkg list-upgradable` 65 行里 4 行是 `Multiple packages (...)` 提示行,`grep -v "^Multiple"` → **61 个真包**,
  减去 6 个 held = **55 个全升成功,0 失败**。判断真实升级数仍只看 `grep -c "^Upgrading"` 日志 = 55 ✓。
- **hold 集合会变**:同是这台机器,09-28 时 luci 家族(`luci-base`/`luci-mod-*`/`luci-compat`/`luci-app-firewall`/
  `luci-app-upnp`/`luci-i18n-*-zh-cn`)在 604 个 hold 里、只能显式 `opkg install` 绕过;10-03 再查已经**不在 hold 里**,
  可随 `opkg upgrade` 整体同版升级 —— 所以**不要照抄上次的"luci 被劈成两半"结论,每次都现查一遍**:
  `awk "/^Package:/{p=\$2} /^Status:.*hold/{print p}" /usr/lib/opkg/status` 存成 hold.txt,再
  `awk "NR==FNR{h[\$1];next} (\$1 in h){print \$1}" hold.txt upgradable.txt` 求交集。
- 这次被 hold 且可更新的只剩 6 个:`base-files`(61~2026073111 → 1674~…,固件自建版,别动)、
  `libopenssl3`/`openssl-util`/`libopenssl-legacy`/`libopenssl-conf`、`libmbedtls21`。全部按规则跳过。
- 本轮唯一 `Collected errors` = `resolve_conffiles: Existing conffile /etc/config/luci is different …
  new conffile will be placed at /etc/config/luci-opkg`(**正常**,用户的 /etc/config/luci 保留)。
- 其他一并升级:`liblzma`/`xz`/`xz-utils` 5.6.2→5.8.3、`zoneinfo-core`/`zoneinfo-asia` 2026b→2026d。
- 升完 `/etc/init.d/rpcd restart; /etc/init.d/uhttpd restart`,再验:`luci.js=200`、
  `ubus -v list luci | grep -c getMountPoints` = 1、`ubus call luci getMountPoints "{}"` 返回真实挂载表、
  `find /www/luci-static /usr/share/luci /usr/share/rpcd /etc/init.d -type f ! -perm -044` 为空、
  sing-box/chinadns-ng 在跑 + `google=200`/`baidu=200`。
- 该机 passwall 26.10.1 的菜单是**经典 Lua 控制器** `/usr/lib/lua/luci/controller/passwall.lua`,
  不在 `/usr/share/luci/menu.d/`(只有 acl.d/luci-app-passwall.json)—— 别照着没有 menu.d 文件就判断安装残了。

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
- ⚠️ **新版 Open-Box 把前端改名了**(2026-10-03 实测):`/www/luci-static/resources/view/openbox/` 里
  只剩 `main.js`(113 KB),旧的 `status.js` 已不存在 → 照老 URL 探测会拿到 **404**,那是改名不是权限复发。
  判断前先 `ls -la /www/luci-static/resources/view/openbox/` 看真实文件名,并 `cat /usr/share/luci/menu.d/luci-app-openbox.json`
  确认菜单 `action.path`(应为 `openbox/main`)。该机 Open-Box 会**自己更新**(19:03 整套文件时间戳刷新,
  `crontab -l` 里没有对应任务),所以每次排查先看时间戳再下结论。
- **一次扫干净所有权限坑**(比背文件清单靠谱):
  `find /www/luci-static /usr/share/luci /usr/share/rpcd /etc/init.d -type f ! -perm -044`
  (输出为空才算干净;修完再跑一遍复核)。
- 两个服务的正确状态:`openbox`(内核/透明代理侧)**inactive + 未 enable 是对的**(该机透明代理归 passwall);
  `openbox-panel`(node 面板,0.0.0.0:2026)应 running + enabled。
- 检查端口用 netstat -tlnp,BusyBox 无 ss 命令(ss 误报 NO_LISTEN)。
- 安装/升级前:该机 passwall 常驻启用,Open-Box 启内核前必须停 passwall,双透明代理会抢防火墙/DNS。
- 面板 http://192.168.50.5:2026,首次访问强制设管理密码;LuCI 兜底页在 服务→Open-Box。
- SSH 直连 GitHub raw 可达(301 正常),78MB 资产下载建议 --mirror(ghfast.top 已验证可用)。

## ⚠️ 面板里的「更新」按钮失败 = api-cache JSON 里没有 .ipk 资产(2026-10-16 实证)

症状:旧版页面(设置 → 应用更新)点「更新」→ 弹 `更新失败：未知错误`,而**手动下 ipk 装完全正常**。
用户看到的就是这句话(例:"Passwall 版本【 26.10.4-1 】 更新失败")。

机制(`/usr/lib/lua/luci/passwall/api.lua`):
- `to_check_self()` 从 `https://github.com/Openwrt-Passwall/openwrt-passwall-packages/releases/download/api-cache/<name>-release-api.json`
  取"最新版"信息,非 apk 系统要求资产名以 `23.05-24.10_` 开头**且**以 `.ipk` 结尾;
- 匹配不到就 `return {code = 1}`(**不带 error 字段**)→ 前端 JS 就显示原文 `更新失败` + `未知错误`。
  "未知"就是这么来的,不是网络/代理报错。
- 成功路径:下载到 `/tmp/passwall_download.<id>{1,2}` → `to_install_self()` →
  `/usr/share/passwall/luci_update.sh` → `opkg install`;状态写 `/www/luci-static/resources/passwall-update/<id>.json`。
  看不到这些临时文件/状态目录,说明失败在**匹配或下载**阶段,根本没进安装。

诊断(30 秒,写完就能下结论):
```sh
curl -skfL -o /tmp/pw-api.json \
  "https://github.com/Openwrt-Passwall/openwrt-passwall-packages/releases/download/api-cache/passwall-release-api.json"
grep -o "\"name\": \"[^\"]*\"" /tmp/pw-api.json    # 26.10.16-1 只有 25.12+_*.apk 两条
grep -c "23.05-24.10_.*\.ipk" /tmp/pw-api.json      # 0 ⇒ 面板必然报"更新失败"
```
**同时确认 GitHub release 页面上的 ipk 是齐的**(直下 858232 字节正常)⇒ 上游 api-cache 快照缺 ipk,
不是路由器/网络问题。结论:面板更新器在非 apk 固件(iStoreOS 24.10)上走不通,**继续走本文的手动 ipk 流程**。

## ⚠️ PassWall 启动死锁：「TCP 未运行」与「脚本已经在运行，不重复运行，退出」排查

### 症状
- 网页面板提示「TCP 未运行」，`pgrep -af "sing-box|xray"` 查不到核心进程。
- `/var/log/passwall.log` 显示 `执行启动延时 XX 秒后再启动!`，之后频繁刷新 `脚本已经在运行，不重复运行，退出.`。
- `ps w` 能看到残留的 `{S99passwall} /bin/sh /etc/rc.common /etc/rc.d/S99passwall boot` 或 `sleep 2`，且 `/var/lock/passwall.lock` 处于 `flock` 锁定状态。

### 根因与排查命令
1. **Lua 块语法污染**：固件补丁或工具可能向 `/etc/init.d/passwall` 注入标记（如 `/lib/system.mark`）。如果误注入到了 `restart()` 函数内部的 `lua -e '...'` 多行字符串中，会导致 `lua` 解释器报错 `unexpected symbol near '/'`。
2. 解释器报错导致锁状态检测代码异常退出，`update_status` 陷入循环 300 次（600 秒）或直接挂死，持锁进程无法释放 `/var/lock/passwall.lock`，后续所有 `start/restart` 都因 `set_lock` 失败而退出。
3. 检查命令：
```sh
# 检查 init 脚本语法
sh -n /etc/init.d/passwall
# 检查 restart 函数中 lua 块内是否混入了非法行（正常应纯净仅包含 require "nixio" 等）
sed -n '55,85p' /etc/init.d/passwall
# 检查持有 passwall.lock 的进程
for p in /proc/[0-9]*; do ls -l $p/fd 2>/dev/null | grep -q "passwall.lock" && echo "PID: ${p#/proc/} $(tr '\0' ' ' < $p/cmdline)"; done
```

### 修复步骤
```sh
# 1. 备份并剔除非法行（例如删除误入 lua 块的 mark 行）
cp /etc/init.d/passwall /etc/init.d/passwall.bak-$(date +%Y%m%d%H%M)
# 修复脚本后校验语法
sh -n /etc/init.d/passwall && echo "SYNTAX_OK"

# 2. 杀掉卡死的老 boot 进程并清除死锁文件
pkill -9 -f "S99passwall"
pkill -9 -f "sleep 2"
rm -f /var/lock/passwall.lock /var/lock/passwall_sub_rule.lock

# 3. 后台重启（必须 nohup + 分步验证，避免 SSH 被防火墙重载打断）
nohup sh -c "/etc/init.d/passwall restart > /tmp/pw-restart.log 2>&1" >/dev/null 2>&1 &
sleep 25

# 4. 验证服务与分流
pgrep -af "sing-box|xray|chinadns"
curl -s -o /dev/null -w "%{http_code}\n" https://www.google.com   # 应为 200
```

---

## ⚠️ 透明代理恢复后，手机端（Google Play 商店等）依然提示「请重试」

### 原因
1. **应用进程缓存了网络故障**：Android 系统与 Google Play 商店（`com.android.vending` / Google Play 服务）在断网期间遭遇超时后，界面与连接组件会驻留「不可用」状态，即使透明代理链路已通，也不会自动静默刷新页面。
2. **移动端本地 DNS 缓存**：断网期间手机可能缓存了解析失败或被污染的 DNS 记录（TTL 内有效）。

### 恢复步骤
1. **多任务划掉杀进程**：在手机后台划掉 Google Play 商店，或进入应用设置点击「强行停止」。
2. **开关飞行模式**：手机开关一次飞行模式，强制刷新系统的 DNS 解析缓存并重建网络连接。
3. **重新打开**：重新点开 Google Play 商店即可正常秒开。

---

## 环境备忘(50.110 实测)

- iStoreOS: 192.168.50.5, dropbear 端口 64891, root, 本机公钥已授权
- 固件: iStoreOS 24.10.8 (OpenWrt 24.10), x86_64, 内核 6.6.144, 商店 = istorex
- opkg 源: 官方 cernet 镜像 + `istore_compat https://istore.istoreos.com/repo/all/compat`(空壳 dummy 包,别指望它有 passwall)
- ttyd 7681 无鉴权开放是安全隐患;用完提醒用户关掉或加鉴权
