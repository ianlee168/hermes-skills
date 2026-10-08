# xiaomi_home「Devices offline / 设备无法局域网连接」每日警告诊断(2026-08-13 实战)

通知原文:"Some devices cannot be connected in the LAN, please check their IP and make sure they are in the same subnet as the HA." — xiaomi_home 集成**每天一次**的局域网连通性检查,报「云端记录的 IP 在局域网连不上」的设备。

## 诊断阶梯(全部只读,先查证)

1. **iStoreOS 租约表**(谁在线、IP 归谁):
   `ssh -p 64891 root@192.168.50.5 'awk "{print \$3, \$2, \$4}" /tmp/dhcp.leases | sort -t. -k4 -n'`
2. **iStoreOS 静态绑定表**(哪些设备 IP 稳定):
   `grep -A4 "config host" /etc/config/dhcp | grep -E "option name|option ip|list mac"`
3. **存活探测**(Unraid 侧):`ping -c1 -W1 <ip>` + `ip neigh show | grep <ip>`
   - REACHABLE = 在线;FAILED / INCOMPLETE = 无 ARP 应答。
   - ⚠️ **小米 WiFi 灯休眠是常态**:有当前租约但 ping 不通 ≠ 离线,大概率误报。租约在 = 设备在网。
4. **跨网段设备**(如 192.168.100.199):主网路由/ARP 表里根本没有 100.x → 必然报。
   - 两种来源:旧网络残留的云端 IP(设备其实已不在该网络/已不存在),或挂了别的路由器/中继的独立网段。
   - 用 `ip route show` + `ip neigh show | grep 100.` 确认主网确实没有该网段。
5. **判断设备是否真在米家**:米家 App 里没有的设备 = 云端遗留(可能只是智能插座之类),直接 HA 里删:设置→设备与服务→Xiaomi Home→设备→⋮→删除。
   - ⚠️ 云端可能重新同步回来 → 提醒用户观察,再犯就得从米家账号/云端层面处理。

## 加静态绑定配方(防 IP 漂移)

```bash
cp /etc/config/dhcp /etc/config/dhcp.bak-YYYYMMDD
uci add dhcp host && uci set dhcp.@host[-1].name='lemesh-light-wy02_mibtF2F3' \
  && uci set dhcp.@host[-1].ip='192.168.50.29' \
  && uci add_list dhcp.@host[-1].mac='B8:50:D8:56:F2:F3'
uci commit dhcp && /etc/init.d/dnsmasq restart
```

## 通知本身

- 标准集成**没有**「关闭此检查」入口;解决设备问题(归位/绑定/删除遗留)才是正解。
- 在线但休眠的设备偶尔被报 = 该集成的已知噪音,不用管。
- 处理顺序:①在线设备 → 忽略;②无租约但有绑定 → 等通电自动归位;③无绑定无租约 → 等上线抓 MAC 补绑定;④跨网段/云端遗留 → 重配 WiFi 或删除。

## 实测案例(2026-08-13,6 台设备)

- 3 台在线(屏幕挂灯 .211 甚至 ping 通)= 误报/休眠。
- 2 台断电(有绑定)= 通电自动拿回原 IP,无需操作。
- 卧室灯 .29:无绑定无租约 → 通电上线后正好拿到 .29 → 立即补静态绑定。
- 「小米空调」@ 192.168.100.199 = 云端遗留(米家 App 无此设备,实为空调插座)→ HA 删除即止。
