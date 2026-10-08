# passwall 国内延迟排查全记录（2026-08-14）

症状：用户报"50.5（iStoreOS 软路由）的 passwall 导致国内 ping 很高，以前都是 2 位数"。
结论：**系统实际完全正常**（国内 TCP/UDP 全直连、DNS 快、路由器自身延迟 4.5-9.5ms）。教训：被 /dev/tcp 计时虚高误导过一轮，tcpdump 才是一锤定音。

## 访问 50.5

```bash
ssh -p 64891 -o ConnectTimeout=8 -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.50.5 '...'
# 凭证在 gbrain concepts/net-topology（密码 见 gbrain concepts/net-topology，密钥免密已配）
```

## 诊断阶梯（按序）

### 1. 本机（.110）粗测 —— 分清 TCP/UDP/ICMP 三类

```bash
curl -s -o /dev/null -w "baidu: connect=%{time_connect}s total=%{time_total}s\n" https://www.baidu.com   # TCP 真实延迟
curl -s --max-time 10 https://myip.ipip.net | head -2     # 出口 IP：=路由器WAN(北京联通)说明没走代理
ping -n 3 223.5.5.5                                        # ICMP 直连参考（⚠️ ICMP 不走 passwall 重定向）
```
- 注意：**ICMP ping 正常 ≠ TCP 正常**（passwall 只重定向 TCP/UDP，ICMP 永远直连）。
- **/dev/tcp 计时陷阱**：`time bash -c "echo > /dev/tcp/223.5.5.5/443"` 在 git-bash 测出 48-57ms 是**进程 fork 开销**，与网络无关（同 IP curl 实测 6.7ms）。凡是 bash 启动开销进计时的测法都不可信。

### 2. 路由器实时状态

```bash
uci show passwall | grep -E "tcp_proxy_mode|udp_proxy_mode|tcp_node|udp_node|dns_mode|dns_shunt|chinadns_ng_default_tag|remote_dns|enabled"
ps w | grep -iE "passwall|sing-box|xray|chinadns" | grep -v grep   # 进程活着？
cat /tmp/etc/passwall/acl/default/TCP_UDP_SOCKS.json              # sing-box 运行态（route.rules/final）
logread | grep -iE "passwall|chinadns" | tail -15                 # 错误日志
```

### 3. nft 分流事实（关键）

```bash
nft list table inet passwall                                     # 全部集合+链
nft list set inet passwall psw_chn_static | grep -cE "[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+"   # 静态 China CIDR 数
nft get element inet passwall psw_chn_static { 223.5.5.5 }       # 精确成员检查（输出 elements={覆盖段} 或 Error）
nft list chain inet passwall PSW_NAT      # TCP: daddr @psw_chn_static ... return = 国内直连；fall-through redirect :1041 = 代理
nft list chain inet passwall PSW_MANGLE   # UDP: dport 443 chn return；其余 chn return → PSW_RULE(tproxy)
```
- psw_chn = 动态集合（2d TTL，dnsmasq 按域名解析结果逐 IP 投喂）；psw_chn_static = 静态 chnroute CIDR（~1335 段）。
- 关键规则带 `meta mark != 0x50535731`（PSW1 标记包跳过直连）。
- chnroute 数据文件：`/usr/share/passwall/rules/chnroute`（4324 行，升级 8/12 时刷新）。

### 4. 决定性验证：tcpdump（区分直连 vs 代理）

```bash
# 路由器上后台抓包
ssh -p 64891 ... root@192.168.50.5 'tcpdump -i any -nn "host 223.5.5.5" > /tmp/cap.txt &'
# 从 .110 发连接
timeout 4 bash -c "echo > /dev/tcp/223.5.5.5/443"
# 看结果
ssh -p 64891 ... root@192.168.50.5 'cat /tmp/cap.txt'
```
判读：`pppoe-wan Out ... > 223.5.5.5.443: Flags [S]` = **直连出 WAN**（5ms 完成握手）；出现 `> 127.0.0.1.1041` 或 SYN 无回应 = **被代理**。

## 结论判定

- 本案例全链路正常：静态集合覆盖、动态集合投喂、TCP/UDP 国内直连规则、DNS(8ms)、路由器自身 4.5ms。
- 用户仍报高时 → 先问 **哪个设备/哪个目标/多少 ms**，再决定抓哪个目标（可能是升级瞬间抖动、特定 IP 不在 chnroute、或手机端 DoH 问题）。
- 8/12 升级（26.7.1→26.8.12-r1）前后配置一致（tcp_proxy_mode='proxy' 一直是），数据文件在升级时刷新 —— 若怀疑升级破坏，对比 `F:/unraid-backup/istore-config-full.tar.gz`（8/6 备份，仅含 /etc，不含 /usr/share 规则文件）。
