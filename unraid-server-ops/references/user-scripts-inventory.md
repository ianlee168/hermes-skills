# Unraid user scripts 盘点与清理(2026-09-09, 50.1)

## 结构
- 脚本目录:`/boot/config/plugins/user.scripts/scripts/<name>/`(每个目录含 `script` + 可选 `description`/`name`/`typescript` 运行输出)
- 调度:`/boot/config/plugins/user.scripts/schedule.json`(`frequency: disabled|hourly|daily|custom`)
- 插件包 `user.scripts-YYYY.MM.DD-x86_64-1.txz` 别动。
- 一键清单:

```bash
ssh root@192.168.50.1 'D=/boot/config/plugins/user.scripts/scripts; for d in $D/*/; do n=$(basename "$d"); printf "%-24s %s 行 改于 %s\n" "$n" "$(wc -l < "$d/script")" "$(date -r "$d/script" +%F)"; done; cat /boot/config/plugins/user.scripts/schedule.json'
```

## 2026-09-09 盘点结果(清理前 6 个,全部未设计划)

| 脚本 | 判定 | 依据(实测) |
|---|---|---|
| Docker_Proxy | ❌ 移走 | `sed` 往 `/etc/rc.d/rc.docker` 注入 `https_proxy=http://192.168.50.10:9090`(该文件每次开机重建→注入不持久);50.10:9090 已 `Connection refused`(主机 ping 通) |
| Gemini_HA_Control | ❌ 移走 | `HA_URL=http://192.168.50.1:8123` 已拒绝(HA 实际在 50.206:8123);脚本内**明文 Gemini key + HA token** |
| delete.ds_store | ⚠️ 移走 | 全数组仅 1 个 `.DS_Store` |
| delete_dangling_images | ✅ 保留 | 实测清掉 15 个悬空镜像 |
| immich update | ✅ 保留 | Immich 容器在跑(`IMMICH_VERSION=v3.1.0`) |
| viewDockerLogSize | ✅ 保留 | 一行诊断命令 |

## 清理做法(可回滚,不用 rm)

```bash
D=/boot/config/plugins/user.scripts/scripts
B=/boot/config/plugins/user.scripts/scripts.bak-20260909
mkdir -p $B; mv $D/<name> $B/
cp /boot/config/plugins/user.scripts/schedule.json{,.bak-20260909}
# 再手写 schedule.json 只留现存脚本条目;用 php 校验:
php -r '$j=json_decode(file_get_contents("/boot/config/plugins/user.scripts/schedule.json"),true); echo json_last_error()===JSON_ERROR_NONE ? count($j) : json_last_error_msg();'
```

恢复:`mv $B/<name> $D/` + 把条目加回 `schedule.json`。

## 坑
- **移动脚本后必须同步删 `schedule.json` 里的条目**,否则插件里留悬挂引用(条目 disabled 时无实际危害,但界面/后续清理会乱)。
- `docker rmi $(docker images -q -f dangling=true)` 若有**正在运行的容器**用着某个无标签镜像,会报 `conflict: image is being used by running container`——正常,剩的 2 个(114MB+756MB)不用管。
- 脚本里的明文凭据在 `/boot`(FAT32 明文可读):移走只是不再运行,**要彻底处理得在服务端吊销/重发 token**。
- 顺带实测:`docker system df` → 镜像 37.28GB(可回收 19.18GB)、**卷 503 个共 60GB 其中 58GB(96%)未使用**——下次清理优先看卷,不是镜像。
