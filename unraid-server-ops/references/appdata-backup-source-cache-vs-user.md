# appdata 备份源: 缓存视图 vs 合并视图 (2026-09-01)

## 事故链(差点误删 481 个有效备份文件)

背景: 每日 04:00 增量备份 cron 后,用户批准清理"陈旧文件"。初判依据:
- 04:06 快照: `rclone lsl unraid:/mnt/cache/appdata` 只有 25 文件 / 65.6 MiB
- 本机 F:/unraid-backup/appdata: 853 文件 / 488M
- 差集 → 828 个"陈旧"文件(按大小+路径逐一比对后实算 481 个;其余 372 个匹配上了第二次 lsl 的 1011 条)

动手前复核发现矛盾: 同一命令第二次跑出 1011 条!ssh 双视图取证:
- `/mnt/cache/appdata`(缓存视图): 775 文件 / 103M,只有 7 容器 (emby/go2rtc/nodebb/postgres/qbittorrent/qinglong/yyb-go)
- `/mnt/user/appdata`(合并视图): **149,466 文件 / 147G / 40+ 容器**
- 抽查 qbittorrent `BT_backup/*.fastresume`、postgres `base/`(1,13779,13780,16384)在合并视图中全部存在且当天仍在更新 → 481 个"陈旧"文件全是有效数据

根因: **Unraid mover 在缓存↔阵列间搬移文件**,缓存视图是移动靶(04:06 恰好赶上 mover 空窗);本地备份是历次缓存快照的累积,"文件从缓存消失" ≠ "数据没了"。

## 真实 docker appdata 构成 (2026-09-01, /mnt/user/appdata)

| 容器 | 大小 | 备注 |
|---|---|---|
| frigate | 97G | 录像存储(大媒体) |
| immich | 45G | 照片库(大媒体) |
| qinglong | 920M | |
| netdata | 858M | |
| emby | 857M | |
| hermes-agent | 757M | |
| nodebb | 400M | |
| homeassistant | 357M | |
| postgres | 338M | 完整数据目录在阵列侧,缓存只挂 96K |
| roonserver | 222M | |
| qbittorrent | 57M | BT_backup 种子状态在阵列侧 |
| yyb-go | 4.6M | |
| ~30 个 0-3M 小容器 | | Authelia/alist/cloudflared/xiaoya 等 |

排除 frigate+immich 后配置 ≈ 5G → 可行的完整配置备份量。

## 正确做法

1. 备份源用 `/mnt/user/appdata`(容器实际读的视图),不用 `/mnt/cache/appdata`
2. 判陈旧/可删: 以 `/mnt/user/...` 全量清单为准,缓存视图不算数
3. rclone 数字异常先 ssh 双视图取证: `du -sh /mnt/cache/<d> /mnt/user/<d>` + `find /mnt/user/<d> -type f | wc -l`
4. 清理三步(红线合规): mv 到隔离区 → 校验当前有效文件与源逐一匹配(大小) → 才 rm 隔离区
5. 本次实际只安全清理了 openwrt 的 2 个 `.partial`(rclone 中断产物,8/26、8/28,各 2.55G;服务器无此文件、主文件同日已重新完整同步)→ 释放 4.75G

## 待决策(2026-09-01 用户未答)

appdata 备份源三选一: ① 改 /mnt/user/appdata 排除 frigate/immich(≈5G,推荐) ② 全量 147G ③ 维持缓存视图(不完整)。未决策前 cron `aeee6a87fd76` 不动,仍按现配置运行(会继续漏备 ~30 个容器,但不影响现有数据安全)。