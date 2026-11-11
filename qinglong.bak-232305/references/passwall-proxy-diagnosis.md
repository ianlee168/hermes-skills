# 判断容器流量是否真走代理 + PassWall 域名强制直连

触发场景: 青龙/内网容器访问国内服务(京东签到等)被风控,怀疑代理出口漂移或被劫持。Unraid 默认网关是软路由(50.5),容器所有出网流量都过 PassWall。**先诊断再下结论,别急着让用户重抓 cookie。**

## 判断「流量是否真走代理」

DNS 解析出国内 IP 不代表连接直连(透明代理可劫持)。用 IP 回显服务对比出口:

- 国内服务回显 `curl -s https://myip.ipip.net` → 显示真实出口(如"当前 IP:123.114.x.x 来自于:中国 北京 联通")= 直连
- 国外服务回显 `curl -s https://api.ip.sb/ip`(或 ipinfo.io/ip)→ 显示代理节点 IP(如韩国 Oracle)
- **两个结果不同 = 分流正常**(国内直连/国外代理);两个都海外 = 走了代理
- 延迟佐证: 国内 API ~0.03-0.05s、google ~0.5s+ = 分流正常
- 别用 ip.cn 等查 IP 的站(被墙 302);myip.ipip.net / api.ip.sb 可用

结论意义: 分流正常但 cookie 仍被作废 → 根因是调试代理期间短暂全局/换节点留下的**风控标记**(IP 漂移历史),不是当前流量问题;等 24-48h 让标记消退,别反复重抓(越抓越可疑,会升级到面部识别验证)。

## PassWall 域名强制直连(保险:调试代理开全局/换节点时不误伤国内域名)

日常规则模式(chnroute + Direct 规则含 geosite:cn)本来就国内直连;强直连是额外保险。SSH: 50.5 dropbear 端口 64891 root。

```bash
cp /etc/config/passwall /etc/config/passwall.bak-$(date +%Y%m%d_%H%M%S)   # 先备份
uci show passwall | grep -E '=shunt_rules|domain_list|ip_list'             # 找规则名(如 passwall.Direct / passwall.Proxy)
# 逐条追加,别整块重写多行值(嵌套 ssh/引号/awk 必炸);add_list 最稳:
while IFS= read -r line; do
  case "$line" in ''|\#*) continue;; esac
  uci add_list passwall.Direct.domain_list="$line"
done < /tmp/domains.txt
uci commit passwall
/etc/init.d/passwall restart     # 必须重启,sing-box 重新生成 acl 才生效
pgrep -af "sing-box|chinadns"    # 验证核心进程起来了
```

- 条目格式: `domain:jd.com`(后缀匹配通吃子域)、`geosite:jd`(规则库分类)
- 京东全家桶清单: jd.com jd.hk 360buyimg.com 360buy.com jdpay.com jcloud.com jdcloud.com jdglobal.com joybuy.com jingxi.com jdjinxikeji.com 3.cn jd.com.cn + geosite:jd
- 重启只重建代理规则,内网连接瞬断即恢复,不影响其他容器
