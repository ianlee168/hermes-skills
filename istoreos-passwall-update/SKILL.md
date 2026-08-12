---
name: istoreos-passwall-update
description: iStoreOS 路由器上 PassWall 的更新与排查 — ipk 直接安装(不用转 run)、官方仓库迁移、SSH 端口、opkg hold 固件保护、周更 cron。适用 OpenWrt 24.10 / iStoreOS 24.10.x x86_64。
triggers:
  - "passwall 更新"
  - "passwall 版本"
  - "ipk 转 run"
  - "istore 安装 ipk"
  - "opkg hold"
  - "路由器 ssh"
---

# iStoreOS PassWall 更新与排查

## 核心事实(踩过的坑)

1. **ipk 不用转 run**:iStore/iStoreX 本地安装原生支持 ipk(商店逻辑:`.run` 直接执行、其余一律 `opkg install`)。PassWall 本来就是 opkg 装的 → 直接 `opkg install` 升级即可,无需转换。
2. **PassWall 官方仓库已迁移**:`xiaorouji/openwrt-passwall` 已 404 → 新地址 **`Openwrt-Passwall/openwrt-passwall`**。版本号 = 日期式 `YY.M.P`(如 26.8.12 = 2026-08-12)。
3. **PassWall 自带"检查更新"只提示不自更**:"最新版本 X,目前暂不支持自动更新,请自行编译或下载 ipk 手动安装"——这是插件正常行为,不是故障。
4. **选 ipk 匹配 OpenWrt 版本**:仓库 release 资产带 `23.05-24.10` 后缀,须选与路由器 OpenWrt 大版本匹配的(24.10 路由器选 23.05-24.10 包)。
5. **615 个固件自带包被 hold**(opkg flags=0x202):iStoreOS 锁住官方源包防顶掉定制组件。这些包 opkg 报"不能更新"是**正常的,不要强升**。
6. **路由器 SSH 是非标准端口**(dropbear,非 22):本机免密用 `~/.ssh/id_ed25519`,公钥写在 `/etc/dropbear/authorized_keys`(**不是** /root/.ssh)。
7. **ttyd 7681 无鉴权开放**(软路由 Web 终端)——安全隐患,建议加鉴权或关闭。

## 升级流程(opkg 直装,已验证 26.7.1 → 26.8.12-r1)

```bash
# 0. 免密登录(或用密码)
ssh -p <SSH_PORT> root@<ROUTER_IP>

# 1. 查当前版本
opkg list-installed | grep passwall

# 2. 下载两个 ipk(GitHub release 资产,选 23.05-24.10):
#    luci-app-passwall_<ver>.ipk
#    luci-i18n-passwall-zh-cn_<ver>.ipk
# 3. 传到路由器 /tmp
scp -P <SSH_PORT> luci-app-passwall_*.ipk luci-i18n-passwall-zh-cn_*.ipk root@<ROUTER_IP>:/tmp/

# 4. 备份配置(重要!)
ssh -p <SSH_PORT> root@<ROUTER_IP> "cp /etc/config/passwall /etc/config/passwall.bak-$(date +%Y%m%d)"

# 5. 安装(自动解析依赖;缺依赖时先 opkg update 再装)
ssh -p <SSH_PORT> root@<ROUTER_IP> "opkg update && cd /tmp && opkg install luci-app-passwall_*.ipk luci-i18n-passwall-zh-cn_*.ipk"

# 6. 重启服务并验证
ssh -p <SSH_PORT> root@<ROUTER_IP> "/etc/init.d/passwall restart && opkg list-installed | grep passwall"
```

**依赖坑**:缺依赖时(如 `microsocks`)从官方源 `opkg install microsocks` 补装,不要降级。

**验证**:`opkg list-installed | grep passwall` 显示新版本;`pgrep -f sing-box`、`pgrep -f chinadns-ng` 等核心进程在跑。**不要动 xray-core 等二进制**,新版 ipk 不硬依赖具体版本。

## 每周自动更新(只更非锁定包)

```bash
# /root/opkg-weekly-update.sh(已部署,日志 /root/opkg-weekly-update.log)
# cron: 30 4 * * 1  bash /root/opkg-weekly-update.sh
# 逻辑:opkg update → 只升级非 hold 包(615 个锁定包自动跳过)
```

## 排查速查

| 症状 | 原因 | 处理 |
|------|------|------|
| "暂不支持自动更新" | 插件正常行为 | 手动下载 ipk 装(见上) |
| opkg 报"不能更新" | 固件 hold 锁定 | 正常,跳过 |
| PassWall 网页打不开 | 服务没起来 | `/etc/init.d/passwall restart` |
| WebUI 在反代后 | Lucky 反代 | http://<ROUTER_IP>:<LUCKY_PORT>/<user>/ |

## 安全

- 端口 22 外网暴露?软路由在内网,dropbear 非标端口 + 公钥免密已配,密码登录建议关闭
- ttyd(7681)无鉴权,任何人进局域网都能开 Web 终端——**建议加鉴权或关闭**

## 凭证

路由器 root 密码、SSH 端口等敏感值:**存在 gbrain(`concepts/net-topology`),不写进本仓库(公开仓库)**。
