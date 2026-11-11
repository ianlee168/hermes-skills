# 青龙安全审计 / 重装评估 (2026-09-01 实战)

触发: 用户看到脚本横幅警告想重装青龙, 或问"要不要全新安装/数据能否保留"。

## 横幅警告的准确含义
jdpro 脚本横幅: "青龙2.20.2以下版本不要外网访问, 已被爆破可任意登录! 必须要外网的就全新安装新版吧, 升级不行"
→ 阈值 = **2.20.2**。警告对象是: 版本 <2.20.2 **且暴露过公网** 的安装。版本 ≥2.20.2 且纯内网 = 警告不适用。

## 三步审计

### 1. 版本号
```
docker inspect qinglong --format '{{.Config.Image}} | {{.Created}}'   # Created=上次容器重建时间
# 在容器内读真实版本(注意在容器里, 宿主机读不到):
docker exec qinglong sh -c 'grep -m1 version /ql/package.json'   # 例: 2.21.0-16
```

### 2. 是否暴露公网 (当前)
路由器 iStoreOS (ssh -p 64891 root@192.168.50.5):
```
iptables -t nat -L PREROUTING -n | grep -iE '6700|DNAT'    # 无输出 = 无端口转发
ls /etc/config | grep -iE 'ddns|ddnsto|frp|zerotier|tailscale'
# 有 ddnsto 必须看 enabled: cat /etc/config/ddnsto → option enabled '0' = 关闭
```
WAN 入站默认全拒 + 无 DNAT → 纯内网。

### 3. 入侵痕迹 (只读查 database.sqlite)
**用容器 python3 的 sqlite3 模块** — @whyour/sqlite3 node fork 的 .all() 有坑(返回空/坏对象), 别用。
```
docker exec qinglong python3 -c "import sqlite3; db = sqlite3.connect('file:/ql/data/db/database.sqlite?mode=ro', uri=True); ..."
```
表 (2.21 版):
- **Auths** type='loginLog' → info JSON 含 ip/address/status (0=成功 1=失败)。统计全部 (ip,status) 计数, 找出非内网非住宅的成功登录 → 问用户是否本人 (VPN/出差/kooldns 中转会把登录 IP 显示成中转 IP)。
- **Apps** = OpenAPI 客户端, 只应看到用户自建 (system/Boxjs)。多出陌生 app = 危险。
- **Crontabs.createdAt** 按年月分布对账使用史; 重点查可疑登录**之后**是否新建过任务 (后门 cron 是最常见植入)。
- Envs / Subscriptions 全量过目。

## 结论模板
版本 ≥2.20.2 + 当前无公网暴露 + 无可疑植入 → **没必要重装**。
版本是必要条件不是充分条件: 真正要重装的是"旧版(<2.20.2)且暴露过"且查不出/不放心的人。

## 重装保数据 (用户三连问: 有必要吗/能代劳吗/数据保留吗)
- 数据 100% 保留: 任务/环境变量/订阅/配置/脚本/日志全在 bind mount 宿主机 `/mnt/user/appdata/qinglong` = 容器 `/ql/data`。重建容器挂同一目录即可 (查 docker inspect qinglong 确认挂载)。
- 只丢容器内一次性状态 (需重做, 各有手册): apk 图形库 (canvas 编译依赖 247 包)、`pnpm add -g canvas`、pnpm global-bin-dir 配置、/root/.npmrc。node_modules 主目录在 /ql/data/scripts 内会保留。
- 流程: docker pull whyour/qinglong → stop + rm 旧容器 → 同名/同挂载/同端口(宿主6700)重建 → 按 SKILL.md 各节补依赖 → 验证。

## 本机基线 (2026-09-01 审计, 供下次比对)
- 版本 **2.21.0-16**, 容器 2026-07-28 重建; 数据史自 2023-01。
- 无 DNAT、ddnsto 禁用; 85 条登录全内网 + 2023 北京住宅 IP + **1 条 2026-03-09 英国 141.11.42.3 status=0**(待用户确认是否本人 VPN/中转)。
- Apps: 仅 system + Boxjs。Crontabs 2026-03 全月仅 1 个新建 (3/2 竞拍竞猜, 早于那次登录) = 无植入。
- Subscriptions 身份解密: **qingwa(id=2) = smiek2121/scripts**(用户起的名, 死库 522), YYDS=okyyds/yyds(死), kr619=gys619/jdd(死), fake3=faker3, jdpro(活)。→ 以后问"qingwa 停不停"指的是**订阅**不是任务。

## 审计侧坑
- `GET /api/user/info` 未认证时返回 SPA HTML 不是 JSON (探测版本别走这条路)。
- API token 过期会静默返回 HTML 页面, 先确认 curl 结果以 `{` 开头再 json 解析。
