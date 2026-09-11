---
name: unraid-server-ops
description: Use when an Unraid user script fails or half-runs.
---

# Unraid Server Ops — User Scripts & Docker debugging

Home Unraid server: **192.168.50.1**, SSH as `root` (key-based auth from the Windows host). Reachable: `ping 192.168.50.1`; connect: `ssh root@192.168.50.1`.

## Where things live

| Thing | Path |
|-------|------|
| User Scripts plugin scripts | `/boot/config/plugins/user.scripts/scripts/<name>/script` |
| Schedule config | `/tmp/user.scripts/schedule.json` |
| Running/finished markers | `/tmp/user.scripts/running/`, `/tmp/user.scripts/finished/` |
| Plugin runtime copy | `/tmp/user.scripts/tmpScripts/<name>/script` |
| Immich app dir | `/mnt/user/appdata/immich` (`.env`, `docker-compose.yml`) |

Known scripts: `immich update`, `Docker_Proxy`, `Gemini_HA_Control`, `delete.ds_store`, `delete_dangling_images`, `viewDockerLogSize`.

## Debugging workflow (in order)

1. **Read the ACTUAL script on disk**, not what the user pasted — they can differ. Check for CRLF/hidden chars: `cat -A '<script>'` (LF-only fine; CRLF breaks bash).
2. **Test each component step-by-step over SSH** (curl the API, grep/sed on copies, `docker compose config`). Isolate the failing command.
3. **Sandbox-test the real script**: copy script + `.env` + compose to `/tmp/<name>-sb/`, then rewrite its `cd` line to the sandbox (`sed -i 's|/mnt/user/appdata/<app>|/tmp/<name>-sb|'`). Run it there — exposes failures without touching the live install.
4. **Forensics — reconstruct what already ran**: `ls -la --time-style=full-iso` + `md5sum` on `.env`, compose, `*.bak` files. Backup created but `.env` mtime unchanged = the chain died between those steps.
5. **Validate compose from the project dir**: `docker compose -f <file> config` resolves `.env` relative to the compose file's dir, NOT the cwd. Testing with the file in /tmp yields false "variable is not set" errors.

## Pitfalls that silently break update scripts

- **GitHub API `/releases/latest` returns SINGLE-LINE JSON.** `grep '"tag_name"' | cut -d'"' -f4` matches the whole line, so `cut -f4` grabs the wrong field (the API `url`) — LATEST becomes `https://api.github.com/...`. The following `sed -i "s/.../$LATEST/"` dies with `unknown option to 's'` (slashes), the `&&` chain aborts, and the script stops mid-flight: backup made, compose replaced, `.env` never updated, images never pulled. **Fix:** `grep -o '"tag_name":"[^"]*"' | cut -d'"' -f4` plus a `[ -z "$LATEST" ]` guard.
- **Long `&&` chains abort silently.** No output, no error — the user just sees "didn't work". Diagnose with `set -x` or echo-after-each-step.
- **`docker compose pull`/`up -d` may never have run** — check `docker images` for the expected new tag before blaming Docker.

## Deploying a fix safely

1. Back up: `cp '<script>' '<script>.bak-YYYYMMDD'`
2. scp the fixed script up → copy over → `chmod +x`
3. Verify on disk: `head -15 '<script>'`
4. Have the user run it once in the plugin UI; console output "Already on vX.Y.Z" = success path reached.

## Cache layout & backups (inventory as of 2026-08-05)

`/mnt/cache` (nvme, 954G total / ~365G free): `appdata` (docker configs, ~389M — **仅缓存视图**,见下), `domains` (VM vdisks, ~357G), `system` (docker.img ~130G + libvirt.img 1G), `frigate` (surveillance ~906M).

🔴 **`/mnt/cache/...` 只是缓存视图,不是完整数据(2026-09-01 教训:差点误删 481 个有效备份文件)**:mover 持续在缓存↔阵列间搬移文件,`/mnt/cache/appdata` 内容随时在变(实测 04:06 只有 25 文件/66M,半小时后 775 文件/103M)。容器实际读的是合并视图 `/mnt/user/appdata`(147G/40+ 容器)。**判断"陈旧/可删"必须对照 `/mnt/user/...` 而非 `/mnt/cache/...`**;rclone size/lsl 数字异常(如同步日志 Listed 111 却只报 25 对象)时,先 `ssh root@192.168.50.1 "du -sh /mnt/cache/<d> /mnt/user/<d>; find /mnt/user/<d> -type f | wc -l"` 取双视图真相再下结论。完整链条: `references/appdata-backup-source-cache-vs-user.md`。

- **VM snapshot convention**: `<VM>.snapshot-YYYYMMDD-HHMMSS/` dirs under `domains/` hold full sparse `vdisk1.img` copies (e.g. `Hermes.snapshot-20260508-151352`, `immort.snapshot-20260508-150924`). `du -sh` = real usage; `ls -la` = provisioned (sparse) size.
- **docker.img (130G) is NOT the docker backup** — the valuable data is `appdata/` (389M). Back up appdata, not docker.img.
- Never `du` the whole `/mnt/cache` in one shot — it's 587G used; scope per-directory.

## Hardware inventory & slot verification (no case-opening needed)

Run from `ssh root@192.168.50.1`:

```bash
dmidecode -t baseboard | grep -E 'Manufacturer|Product Name'   # motherboard
dmidecode -t slot | grep -E 'Designation|Type|Current Usage|Bus Address'  # PHYSICAL slots incl. EMPTY ones
lspci -tv                                                       # OS-enumerated PCIe tree
lspci -vv -s <bdf> | grep -E 'LnkCap|LnkSta'                    # real link speed/width of a device
lsblk -o NAME,SIZE,MODEL,MOUNTPOINT                             # full disk inventory
cat /proc/mdstat; mdcmd status | grep -E 'mdNumDisks'           # array members / parity check
df -T /mnt/cache; btrfs filesystem show /mnt/cache              # cache FS type + pool layout
```

Pitfalls (all hit live on 50.1):
- **`dmidecode -t slot` → `Current Usage: Available` is NOT trustworthy** — every slot, even the one holding the live NVMe, reads "Available". Its `Data Bus Width` field is also unreliable (reported x2 on a slot running x4). Always cross-check with `lspci -tv` and `/sys/block` symlinks.
- **M.2 socket types**: `Socket 3` = standard NVMe/SATA SSD slot (Key M). `Socket 1-SD` = Key A/E — WiFi/CNVi card slot, x1; physical keying mismatch means an NVMe SSD will NOT fit. A "second M.2" reporting Socket 1-SD is not an SSD slot.
- Count NVMe endpoints with `lspci | grep -i non-volatile` — a populated second slot would enumerate a controller; no extra = no second drive.
- **Parity is not guaranteed**: `mdNumDisks=3` with no parity device → array disks are bare (a dead disk loses everything). Check before assuming any redundancy.
- `_snap_recover/` (197G on 50.1) = btrfs snapshot-recovery residue from 2026-05-09; stale duplicate data, safe to delete with user consent. ⚠️ 它是 **btrfs 只读子卷**(`btrfs subvolume list /mnt/cache` 可见 ID 263),直接 `rm -rf` 满屏 `Read-only file system` 失败;先 `btrfs property set -ts /mnt/cache/_snap_recover ro false` 再删(2026-08-27 实测,用户批准后清掉 197G)。

## Cache disk replacement (user wants SSD-failure protection)

WTR PRO has **only ONE standard M.2 SSD slot** (J3704, occupied by the GLOWAY 1TB). When the user wants to "buy a new SSD" for protection:
1. **Swap workflow** (simplest, what the user usually means): mover cache→array (Unraid UI `mover`), shut down, swap disk, format new cache, mover back; old disk becomes offline cold spare. ~1-2h.
2. **raid1**: spare **PCIe x8 slot J3604 + M.2→PCIe adapter** (~¥20-50) → add disk to cache pool as btrfs raid1. Needs case-open confirmation that the slot area has space.
3. Run `smartctl -a /dev/nvme0n1` on the old disk BEFORE trusting it as a cold spare.
4. Cloud fallback: R2 via WSL `gbrain_r2:` (below).

## VM shows "running" but is unreachable on the LAN — hung-guest diagnosis (2026-08-07)

Symptom: SSH to a VM IP times out; `ping` from the Windows host returns **"Reply from <own-IP>: Destination host unreachable"** = the local machine itself answers for an unresolved L2 target = NO ARP response = the guest's network stack is dead (a live firewall still answers ARP; a dead stack answers nothing). Work the ladder on the Unraid host (`ssh root@192.168.50.1`):

1. **Identify the VM**: `virsh list --all` (note: VM names can contain spaces — quote names in loops), then `virsh domiflist <vm>` → MAC.
2. **Find its current IP**: NO guest agent installed → `virsh domifaddr` returns EMPTY — don't trust it. Cross-ref the MAC against the host table: `arp -a | grep -i 52:54:00` or `ip neigh show`. A bridge entry proves the IP the VM is attached to — NOT that the guest is alive.
3. **Guest alive at L2?** `ip neigh show | grep <ip>` — state **FAILED** = kernel probed, no answer = dead/hung. `arp -n`'s stale `C` entry is misleading; trust `ip neigh` state.
4. **Dead vs alive-but-no-service**: `timeout 3 bash -c "</dev/tcp/<ip>/22"` → **timeout = dead**; **"Connection refused" = alive, just no SSH** (run the same probe on a known-live VM as baseline).
5. **Hung vs frozen vCPU**: `virsh domstats <vm> --cpu-total` twice, ~3s apart. CPU time ADVANCING while the network is dead = kernel hung (soft lockup / D-state storm, classic disk-full symptom) — not a frozen vCPU.
6. **Fix**: graceful `virsh reboot <vm>` (ACPI) usually FAILS on a hung guest — don't wait long. Go to `virsh destroy <vm> && virsh start <vm>` (power-cycle; per the user's delete-consent rule, get OK first — user pre-approved this fallback in-session). Verify after boot: ping → `ssh ianlee168@<ip>` → `systemctl --user is-active hermes-gateway`.
7. **Post-mortem**: reboot wipes kernel logs; without persistent journal/sudo the hang cause may stay unknown. Highest-yield single probe is `df -h` inside the guest (disk full #1 cause) — this case was 50%, ruled out.

Full command transcript + output interpretation: `references/vm-hung-diagnosis.md`.

## VM 被 QEMU 自动暂停 — 磁盘写满 IO error(2026-08-27,50.206 HA)

症状:VM 完全打不开,ping 不通;`virsh list --all` 显示 **paused**(不是 running)。用户会以为"谁暂停了"——没人暂停,是 **QEMU 保护机制**:磁盘写失败(`No space left on device`)时自动暂停 VM 防数据损坏。

排查链:
1. `virsh list --all` → paused;`virsh dominfo <vm> | grep State`
2. **铁证在 QEMU 日志**:`grep -i "IO error" "/var/log/libvirt/qemu/<VM>.log"` → `IO error device='sata0-0-2' ... reason='No space left on device'`。**日志时间是 UTC**(18:04 UTC = 本地 02:04,别误读)
3. `virsh dumpxml <vm> | grep "source file"` 找到报错磁盘 → 本例 `/mnt/cache/domains/HAOS/haos_ova-18.2.qcow2`(cache 上的 qcow2 动态增长,写不动)
4. **找写爆 cache 的元凶**:`df -h /mnt/cache` → `find /mnt/cache -xdev -mtime -2 -type f -size +200M` → 大文件+时间戳对上(qBittorrent 下载的 4K 电影,8/26 21:11)
5. **share 缓存策略**:`cat /boot/config/shares/<name>.cfg` → `shareUseCache="yes"` = 新文件优先落 cache。qBittorrent `/downloads` = `/mnt/user/NAS`(cache-backed)→ 109G 电影全落 cache → 写爆。**同源连带**:frigate 数据库 `disk I/O error` 也是它(别误判成数据库损坏)

恢复:
1. 释放空间:VM 内 `journalctl --vacuum-size=20M`,或宿主侧跑 mover
2. `virsh resume <vm>` → resume 后 guest 可能卡住(网络通但服务没起)→ **`virsh reboot <vm>` 完整重启比 resume 干净**(2026-08-27 实测:resume 后 HA core 起不来,reboot 后正常)
3. 验证:`curl -s -o /dev/null -w "%{http_code}" http://<vm-ip>:<port>/`

HA OS(Home Assistant OS)内部要点:
- **根分区 df 显示 100% 是正常现象**(`/` = erofs 只读镜像 253.8M,Available 0 是只读特性,不是满;别被骗去"清根分区")。可写层在 `/dev/sda7`(/mnt/overlay,几乎空);journal 在 `/dev/sda8`(`/var/log/journal` 单独挂载 = 数据盘)
- **HA 端口是 8123,不是 812**(用户常记错少写 3)
- `virsh console <vm>` 交互登录:ssh -t + pty 后台驱动,HA OS 控制台 **root 无密码**直接登录;上一个会话还挂着时报 `error: Active console session exists for this domain` → 用 **`virsh console --force <vm>`** 强制接管;`ha core info` / `docker ps` 看核心状态;控制台输出挤在一起(无换行),命令用分号分隔、分小步发,输出可能被截断
- HA 系统盘 qcow2 在 cache → cache 满时 HA 先遭殃(HAOS + Hermes 两个 VM 同时被暂停是连锁)

**HAOS VM 磁盘构成**(2026-08-27,用户问"50.206 磁盘为啥用这么多"):
- 三个磁盘文件叠加:`vdisk2.img`(100G raw,**HAOS 外部数据盘**,ext4 LABEL=`hassos-data-dis` PARTLABEL=`hassos-data-external`,实际占 60G,当前未挂载)+ `vdisk2.S<ts>qcow2`(5/11 虚拟机快照,53G 冗余)+ `haos_ova-*.qcow2`(系统盘 27G,真实数据 17.4G)
- 用户看到的"243G"= 虚拟磁盘分配总和(100+53+27+其他),**真实数据只有 ~17G**;`ls -lah` 是逻辑(稀疏)大小,`du -sh` 才是真实占用
- 判断盘上有没有数据:**`blkid /dev/sdb1`** 有 LABEL/TYPE = 有文件系统(别信未挂载状态或 `file -s` 空输出);`qemu-img info <img>` 看虚拟 vs 实际
- **HAOS 的 `/mnt` 是只读(erofs)**,检查外部盘先 `mkdir -p /mnt/data/mnt-test && mount -o ro /dev/sdb1 /mnt/data/mnt-test`(挂到 /mnt/data 下),看完 `umount` 再删目录
- 释放候选:旧快照 `vdisk2.S*.qcow2` 可删(确认无需回滚后,需用户批准);外部数据盘先看内容再决定留不留

mover 行为(2026-08-27 实测):
- 手动触发:`/usr/local/sbin/mover start`(幂等,可重复跑)
- **被占用文件 skip**(4 个 4K 电影 skip:被 emby/qbittorrent 打开);深夜自动 mover 再试
- **domains/ 下 VM 磁盘默认 skip 不移**;appdata 运行中容器的 `.db-wal/.db-shm` 也 skip

预防(用户已确认方向):qBittorrent 已有 `/download02` 挂载(直写阵列盘 Movie01/TV03),**下载大文件选 download02,别落 NAS share(cache-backed)**;`_snap_recover/`(197G,5/9 旧残留)清掉可释放 cache 1/5。

## VM 磁盘移除(detach-disk)实战流程(2026-08-27,HA 旧数据盘 113G)

场景:确认某块 VM 磁盘没用后移除(释放 cache/分配空间)。红线合规:**先 mv 到备份区,确认稳定后再清,不直接 rm**。

```bash
# 1. 优雅关机(等 shut off;VM 名含空格要引号)
virsh shutdown "Home Assistant"
# 2. 确认设备名:virsh dumpxml <vm> | grep -B3 -A8 "vdisk2" → target dev='hdd'
# 3. 从配置移除磁盘(--config = 持久配置;VM 已关机时 detach 默认改配置)
virsh detach-disk "Home Assistant" hdd --config
# 4. ⚠️ 必须验证 detach 真生效:配置里引用计数应为 0
virsh dumpxml "Home Assistant" | grep -c "vdisk2"   # 期望 0
# 5. 文件 mv 到阵列盘备份区(跨盘复制,113G 要 20-40 分钟)
mkdir -p /mnt/disk1/trash-<vm>-<date> && mv "/mnt/user/domains/Home Assistant/vdisk2.img" "/mnt/user/domains/Home Assistant/vdisk2.S*.qcow2" /mnt/disk1/trash-<vm>-<date>/
# 6. 启动 VM
virsh start "Home Assistant"
```

**坑(全部实测)**:
- **`virsh start 7`(数字 ID)失败 `failed to get domain '7'`** — detach-disk 修改配置后域 ID 失效,一律用**域名** `virsh start "Home Assistant"`;`virsh list --all` 里 `Id` 列是 `-`(未运行)时 ID 不可用
- **detach 后必须 dumpxml 验证**:第一次 detach 因命令超时中断,`virsh start` 报 `Cannot access storage file ... No such file` 才暴露配置里还挂着文件;grep -c 归零才算成功
- **大文件 mv 跨盘会拖爆 SSH 超时,但 mv 进程不被杀**(孤儿继续跑):`pgrep -x mv` 确认还活着,用 `while pgrep -x mv; do sleep 20; done` 等待,别重复发起 mv
- 快照链一体:qcow2 顶层(`vdisk2.S<ts>qcow2`)+ raw 底层(`vdisk2.img`)是一块盘的 active layer + backing,删一块必须整盘处理,不能只删一个文件
- detach 后 `virsh start` 若报缺文件,先补 detach 再 start,别手动 edit XML(易错)

## VM↔IP 映射 & 用户报错 IP 先核对(2026-08-27 实测)

```text
MAC 前缀(52:54:00:)  ↔ VM                ↔ IP
cc:8b:ec              Home Assistant      → 192.168.50.206(曾用 50.146,旧 IP)
25:00:a5              Hermes             → 192.168.50.161 ⚠️ 不是 206!
f4:25:61              iStoreOS           → 192.168.50.5
```
查法:`virsh dumpxml "<vm>" | grep -oE "52:54:00:[0-9a-f:]{6}"` ↔ `ip neigh show | grep -i <mac>`(VM 用桥接 br0 时 `virsh domifaddr` 为空,别信)。

- **用户报"某 IP 磁盘/服务有问题"先核对 VM↔IP 再动手**(2026-08-27:用户把 50.161 的磁盘问题报成 50.206;206/161 差一位极易记混,用户自己也承认误导)。**判断线索:HAOS 无 LVM、无 /home** —— 看到"LVM 卷 + / 与 /home 同卷"是标准 Linux 发行版(Ubuntu 等)布局,绝不是 HAOS(其根是 erofs 只读,数据盘在 /mnt/data);`lsblk`/`df` 输出一眼可辨。
- **让用户跑诊断命令前先确认连对机器**:输出含 `community.applications`、`/var/local` 567M、`/boot` = Unraid(50.1)根分区,不是目标 VM;让用户先 `hostname` 验证再跑 du。本机(50.110)→50.161 **无 SSH 公钥**(反向才有:50.161 的公钥已写入 50.110),需要用户在 50.161 上执行或提供凭据。
- **Hermes VM 磁盘**:`vdisk1.img`(150G 底层)+ 活动快照层 `vdisk1.S<ts>qcow2`(实测 182G,VM 运行中所有写入都进它)—— **快照层只增不减**,长期撑爆 cache;VM 磁盘快照层建议定期合并/清理(用户确认后)。

## Hermes VM(50.161)磁盘瘦身 & qcow2 快照链合并(2026-08-27 实测)

**访问凭据先查 gbrain**(`environment/hermes-vm`):用户名 **`ianlee168`(不是 ianlee!)**、50.110 公钥认证已配好 → `ssh ianlee168@192.168.50.161` 直接进。hostname=hermes,Ubuntu LVM `/dev/mapper/ubuntu--vg-ubuntu--lv 243G`。**先查 gbrain 再试 SSH,别瞎猜用户名浪费时间**。

VM 内部磁盘满排查(用户目录大头):
```bash
sudo du -x -h --max-depth=2 / 2>/dev/null | sort -rh | head -15   # 典型:168G / 里 148G 在 /home/<user>
sudo du -x -h --max-depth=2 /home/<user> 2>/dev/null | sort -rh | head -15
```
Hermes 备份机制:每天自动生成 `~/hermes_backups/`(backup_*.zip + hindsight_backup_*.zip,2.4G/个);Hermes 清理旧备份时丢进 `~/.hermes/_trash_hermes_backups_<yyyymm>/`(**垃圾桶实测 60G 不自动清**)。保留策略:留最近 2-3 个,其余删:
```bash
rm -rf ~/.hermes/_trash_hermes_backups_202608
cd ~/hermes_backups && ls -t | tail -n +4 | xargs rm -f
```
旧 venv:删前 `ps aux | grep -i open-webui` 确认在用的那个(bak-* / 旧 env 可删)。删除红线:用户批准 + 给清单(这些都是可再生副本,丢失风险极低)。

**qcow2 快照链 & 镜像收缩(核心:VM 内部删文件 ≠ 镜像文件变小!)**:
- Hermes 磁盘 = 三层链:`vdisk1.img`(150G raw 底层)+ `vdisk1.S<ts1>qcow2`(小中转 98M)+ `vdisk1.S<ts2>qcow2`(活动层,VM 运行所有写入都进它,**只增不减**,实测 182G)
- `qemu-img info --backing-chain <活动层>` 看全链;区分虚拟大小(250G,扩容过)/ 链实际占用(225G)/ 内部真实数据(65G)
- **合并+收缩 = convert 整链成单文件**(新镜像 ≈ LVM 层已分配大小,**≠ 文件系统真实数据**,见下):
  ```bash
  virsh shutdown "Hermes"   # 优雅关机可能卡住(服务 hang,网络停了还不退出)→ ssh 进去 sudo -n shutdown;还不行 virsh destroy(ext4 journal 保护,风险低,2026-08-27 实测)
  cd /mnt/cache/domains/Hermes
  qemu-img convert -p -f qcow2 -O qcow2 vdisk1.S20260511173333qcow2 vdisk1-merged.qcow2   # 15-30 分钟,后台跑 + notify
  virsh detach-disk "Hermes" hdc --config && virsh attach-disk "Hermes" /mnt/cache/domains/Hermes/vdisk1-merged.qcow2 hdc --config --driver qemu --subdriver qcow2 --targetbus virtio
  # attach 后检查 boot order 是否保留:virsh dumpxml "Hermes" | grep -A8 "vdisk1-merged"
  virsh start "Hermes"   # 用域名!数字 ID 在 detach 后失效
  ```
- 旧链文件(225G)验证 VM 正常后:mv 到阵列盘备份区(红线先备份)→ 用户确认后清
- 坑:**qemu-img 打不开镜像 = VM 还在跑**(qemu 进程锁镜像),先关机;convert 目标文件也放 cache,cache 需有 ≥ 目标大小剩余空间;convert 是流式写入,峰值 = 目标大小
- **convert 结果 ≠ 内部真实数据(2026-08-27 实测:内部 65G 数据,convert 出 178G)**。原因:guest 是 **linear LVM**(非 thin),文件系统删除只释放文件系统层,LVM 卷不把块还给镜像 → discard 不传播 → qcow2 认为全部分配。**guest 里 `fstrim -av` 对 linear LVM 无效**(trim 停在 LVM 层,镜像文件不缩小)。想缩到真实数据大小需改 thin LVM 或文件系统层零化,为省空间不值当冒险——接受 convert 结果即可(本例 225G→178G 已省 47G);验证 `du -sh <img>`(真实占用),`ls -lah` 是逻辑大小。
- **🔴 detach+attach 丢 boot order 的连环坑(2026-08-27 最深的一坑)**:`virsh attach-disk` 不带 boot order → VM 启动时**优先从 cdrom(ubuntu ISO)启动 live 环境**,根本不是磁盘系统!症状签名(三者齐备 = boot 错盘):① **host key 每次重启都变**(live 环境每次全新);② **guest 里 sshd 的 auth.log 不再更新**(时间停在强制断电前);③ **key 认证全失败、提示要密码**(live 环境没有你的 authorized_keys)。修复:`virsh dumpxml <vm> > /tmp/vm.xml` → sed 在磁盘的 `<target dev='hdc' bus='virtio'/>` 行后插 `<boot order='1'/>`(⚠️ bash 双引号里 `\x27` 不转义会匹配失败,直接写 `'hdc'` 字面量)→ `virsh define /tmp/vm.xml` → `virsh start <vm>`(用域名,detach 后数字 ID 失效)。cdrom 保留 `boot order='2'` 无妨。改完验证:`virsh dumpxml <vm> | grep -c "boot order"` 应为 2,且磁盘段含 `order='1'`。正确 boot 到磁盘系统后 host key 恢复稳定、key 登录恢复。
- **qemu-nbd 离线改 guest 文件(免密码救援,2026-08-27 实测)**:VM 关机后 `qemu-nbd -c /dev/nbd0 <img>` → `vgchange -ay <vg>` → `mount /dev/<vg>/<lv> /mnt/<fix>` → 改文件(如追加公钥到 `.ssh/authorized_keys`,权限 600、home 750、owner uid 匹配)→ `umount` + `vgchange -an` + `qemu-nbd -d` → `virsh start`。用于 guest 登录凭据失效/忘记密码时恢复 SSH。改完若 host key 变了(known_hosts 旧记录)→ `ssh-keygen -R <ip>` + `-o StrictHostKeyChecking=accept-new` 重连。Unraid 无 python3,改 XML 用 sed 别用 python。

## HAOS VM: "虚拟化的操作系统映像不正确" unsupported warning (2026-08-13, 50.206)

Symptom: daily Supervisor banner "Unsupported system — Incorrect image for virtualization" (reason `virtualization_image`). Root cause on this box: the HA VM boots a **bare-metal image** (`haos_generic-x86-64-13.0` in `/mnt/cache/domains/HAOS/`) inside KVM; HAOS's virtualization line is `haos_ova-*` (qcow2=KVM, vmdk=VMware, vhdx=Hyper-V, vdi=VirtualBox). **TRAP: Unraid names the COW overlay `...S<ts>qcow2` over a `.img` base — the format suffix says nothing about image family; the generic kernel is baked in, so no format conversion fixes it.** Diagnosis: `virsh dumpxml '<vm>' | grep 'source file'` → check family; `curl -s https://api.github.com/repos/home-assistant/operating-system/releases/latest | grep '"name"'` → current KVM asset (`haos_ova-18.2.qcow2.xz` as of 2026-08). Impact is cosmetic (banner + "unsupported" = no official support; add-ons/automations keep working); official fix = reinstall with ova image + restore from backup, no in-place path. Full chain + HA docs raw-markdown fetch trick: `references/haos-vm-image-mismatch.md`.

## HA 仪表盘清理(2026-08-13)

- UI 模式仪表盘存在 `.storage/lovelace_dashboards`(id 形如 `dashboard_yfwl01`),**设置→仪表盘 行菜单可直接删**,删完侧边栏立即消失,无需动 YAML、无需重启。
- ⚠️ 行菜单只有「设为默认/编辑」**不代表 YAML 模式**——本会话据此推断"需改配置"是错的,用户在 UI 直接删成功了。判 YAML 的唯一可靠法:查配置(备份包内 configuration.yaml/dashboards.yaml)里有没有该 dashboards 定义。
- 用 computer_use 驱动 Chrome 里的 HA 页面(读侧边栏、点菜单)见技能 `ax-tree-ui-driving`。

## Web lookups via the server when local web tools are blocked

If web_search/web_extract are unavailable and the local browser hits captchas (Baidu/Google) or GBK decode errors (Bing/JD/smzdm), the Unraid box's domestic broadband is a usable vantage point:

```bash
ssh root@192.168.50.1 "curl -s -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0' 'https://www.sogou.com/web?query=<urlencoded>' -o /tmp/sg.html"
```

- sogou returns real results on the first hit, then rate-limits (~533-byte response on the 2nd); cn.bing.com works but splits CJK query terms without cookies → garbage results.
- GBK-encoded pages (e.g. ZOL product search): `iconv -f gbk -t utf-8 <file>`.

## Cloud backup path (as of 2026-08-05)

- The **server's own rclone.conf is EMPTY** (`/root/.config/rclone/rclone.conf`, 0 bytes) — no remotes on the Unraid box.
- Working cloud channel is **WSL on the Windows host (50.110)**: remote `gbrain_r2:` → Cloudflare R2, bucket `huawei-car-raw`, endpoint `https://8bc8658cbb45f90275fd62d411b35723.r2.cloudflarestorage.com`. Run `wsl -e bash -lc "rclone listremotes"` from the Windows host.
- **Google Drive remote `hermes_backup` (referenced by the user's gbrain-backup script) no longer exists** in WSL rclone config — that script now fails its remote check; a fresh GD remote **`gdrive` is configured ON the server** (headless OAuth completed 2026-08-06, token pasted, `rclone lsd gdrive:` verified; 5TB account, 4.6TiB free — see `references/rclone-gdrive-headless-oauth.md`).
- **Google Drive is the user's preferred cloud target for cache backups — account has 5TB free space (confirmed 2026-08-05), so 287G of important data fits at $0 incremental cost** vs R2's $1-4/mo. The server reaches Google DIRECTLY over its domestic broadband (accounts.google.com 302 in ~0.6s, drive.google.com reachable) — no proxy needed for the upload itself.
- R2 pricing: $0.015/GB-month storage, 10GB free tier, free egress (71.4G of cache backups ≈ $1.1/mo).
- Upload route options: copy the WSL rclone section onto the server, or rsync server → Windows host → R2 via WSL.

### Upload bandwidth reality check (2026-08-06) — cloud backup of BIG data is NOT viable here

Measured from the server's domestic broadband (download fine, upstream throttled):

| Target | Upload | 287G ETA |
|---|---|---|
| Google Drive (raw token + curl) | 104 KB/s | ~32 days |
| Cloudflare R2 (`gbrain_r2`) | 153 KB/s | ~22 days |
| `speed.cloudflare.com/__up` (100M POST) | 259 KB/s | ~13 days |
| Download control (`dl.google.com`) | 5 MB/s | — |

**Rule for this line:** upstream to ANY overseas target is ~1-2 Mbps → only payloads ≤ ~3G are practical to push to the cloud (appdata 389M + libvirt 1G + frigate 906M ≈ 2.3G ≈ 3h at 2Mbps). VM disks (287G) go the LOCAL route — either `Cache disk replacement` (new SSD) or the rclone-SFTP pull to the Windows host's F: drive (section below). Diagnose BEFORE committing to a multi-day upload:
- Bypass rclone to separate client-id throttling from network QoS: `grep -oP 'access_token.:.\K[^\"]+' /root/.config/rclone/rclone.conf | head -1`, then `curl -X POST -H "Authorization: Bearer $TOKEN" --data-binary @5MB.bin 'https://www.googleapis.com/upload/drive/v3/files?uploadType=media'` and read `%{speed_upload}` — HTTP 200 + ~100 KB/s = network QoS, NOT a config bug (do not blame the shared internal client_id).
- Upstream probe: `curl -X POST --data-binary @100MB.bin 'https://speed.cloudflare.com/__up' -w '%{speed_upload}'`.
- Control: `curl -L 'https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb' -o /dev/null -w '%{speed_download}'`.

## Local LAN backup — rclone SFTP pull to the Windows host (2026-08-06, THE working route for big data)

The user's chosen target is the Windows host's **F: drive (3.7T, ~1.2T free)**. Pull over SSH with Windows rclone — no server-side changes, no SMB. Server needs nothing; local rclone v1.74 is already at `C:\Users\ianle\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_...\rclone-*\rclone.exe` (in PATH).

```bash
rclone config create unraid sftp host 192.168.50.1 user root key_file "C:/Users/ianle/.ssh/id_rsa"
rclone lsd unraid:/mnt/cache/                 # verify
rclone copy unraid:/mnt/cache/appdata "F:/unraid-backup/appdata" --stats 15s -v
rclone copy unraid:/mnt/cache/domains "F:/unraid-backup/domains" --stats 30s -v   # big one
```

- **Speed ~64-71 MiB/s** (gigabit LAN incl. SSH overhead) → 287G ≈ 75 min. qBittorrent `ipc-socket` errors (`SSH_FX_FAILURE`) are normal — runtime socket, not a real file; ignore.
- **Windows rclone rejects MSYS paths in config values**: `key_file /c/Users/ianle/.ssh/id_rsa` → "failed to read private key file ... The system cannot find the path specified". Use native `C:/Users/ianle/.ssh/id_rsa`. Also: Windows rclone reads `%APPDATA%\rclone\rclone.conf`, NOT WSL's `~/.config/rclone` — `rclone listremotes` on the Windows side shows NOTHING even though WSL has `gbrain_r2`.
- **Sparse-file caveat**: SFTP backend has no sparse handling — a vdisk tree that `du`s 357G but is logically 664G transfers as 664G. F: drive must fit LOGICAL size; ETA ≈ 2.5-3h, not 1.2h.
- **Consistency**: copying a RUNNING VM's vdisk = hot copy (restore may need fsck). Clean backup = stop VM → re-run `rclone copy` (incremental, only the delta, minutes) → start VM. NEVER stop `openwrt` if it is the soft-router — the whole LAN dies.

Why NOT SMB copy (all three dead ends hit on 50.1):
- User shares (`appdata`/`domains`/`system`) have `shareExport="-"` in `/boot/config/shares/<name>.cfg` — SMB/NFS export DISABLED; only disk shares (Movie01/TV03/NAS/flash) are exported. Enabling needs cfg edit + `rc.samba restart` (briefly drops Movie01/TV03 clients).
- Windows 10/11 blocks guest SMB by default: `AllowInsecureGuestAuth` under `HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters` is unset; setting it needs admin — `powershell Start-Process powershell -Verb RunAs -ArgumentList ...` pops a UAC prompt the user must click.
- `net view \\\\192.168.50.1` from git-bash errors 1702 (GBK-garbled output, no session established).

## Backup freshness, failure recovery & the cron shutdown-window pattern (2026-08-06)

- **F: backup is a point-in-time snapshot — staleness IS data loss.** If the SSD dies on day N, an untouched backup loses N days of changes. User's decision (SSD prices surging): DON'T buy the SSD now; keep the F: backup FRESH instead. Required upkeep: periodic incremental re-sync (re-running `rclone copy` = delta only; for a RUNNING VM the active vdisk re-copies every run and the job never "finishes" until the VM stops — expected) plus a monthly shutdown-window consistency pass.
- **SSD death does NOT require an immediate SSD purchase.** Array disks had ~12T free (disk1 3.8T / disk2 4.5T / disk3 3.8T). Recovery path when the cache SSD dies: restore domains+appdata from F: onto the array (shares move off cache; Unraid keeps running, just slower) → buy the new SSD whenever the price is right → mover back. Present this as the "wait out the price surge" plan to a cost-sensitive user.
- **Automated shutdown-window backup = Hermes cronjob** (one-shot, e.g. 03:00 local): `virsh shutdown Hermes` + `virsh shutdown "Home Assistant"` (90s grace, `virsh destroy` fallback; NEVER touch `iStoreOS` — soft-router, whole LAN dies), re-run the incremental `rclone copy`, verify `rclone check --size-only`, `virsh start` both, report. Self-contained prompt template: `references/automated-vm-backup-cron.md`.
- **PITFALL — rclone log timestamps are UTC; local clock is UTC+8.** Misreading `--stats`/`-v` timestamps as local time shifts "now" 8h into the past → a cronjob scheduled for "03:00" was actually set for an hour that had ALREADY PASSED. One-shot cronjobs set in the past stay `state=scheduled` with `last_run_at=null` and NEVER fire — silently. Before scheduling: `date '+%Y-%m-%d %H:%M:%S %Z (%z)'` on the Windows host AND the server; after create/update, verify the cronjob response's `next_run_at` is a FUTURE local time.
- **Hermes cronjob `deliver` defaulted to `local`** this session (no live channel) — results saved but not delivered; update with `deliver='origin'` after create if the report must come back to the chat.

### Final backup scope decision (2026-08-06) — ask BEFORE assuming scope

- The user's actual concern is ONLY **openwrt (soft-router vdisk) + docker appdata**. Everything else was progressively dropped: Hermes (daily changes too large → backup cost > value; hot-copy md5 failures on its qcow2 layers are the norm), Home Assistant, HAOS, and both snapshot dirs. After copying, all four were DELETED from F: (570G, explicit user consent; server originals untouched) — F: now holds only `domains/openwrt` (11G) + `appdata` (390M).
- **Lesson: ask which VMs/data the user actually cares about BEFORE planning the back-up.** The 287G "important data" plan was 25× the real requirement (11.4G).
- **Daily incremental sync cron `aeee6a87fd76` (02:00 local, recurring):** `rclone copy unraid:/mnt/user/domains/openwrt F:/unraid-backup/domains/openwrt --stats 30s -v` + `rclone copy unraid:/mnt/user/appdata F:/unraid-backup/appdata --stats 30s -v --ignore-errors --exclude "**/*_fifo" --exclude "/netdata/cache/**"`. **源必须写 `/mnt/user/...`(合并视图),不是 `/mnt/cache/...`**;两个 `--exclude` 是必需的 —— netdata 常驻 FIFO 会让 rclone 永久挂起(详见 `references/rclone-backup-verify-and-cleanup.md`)。**排期 02:00 不 04:00**: 本机每日 04:00 关机,排在关机点等于永远赶不上。openwrt 是软路由,永不停机;热拷贝没问题(配置为主,增量极小)。
- ✅ **appdata 备份源 = `/mnt/user/appdata`(已定案并落地在 cron 里)**:`/mnt/cache/appdata` 只是缓存视图(7 容器/103M),真实合并视图 = 147G/40+ 容器(frigate 97G 录像 + immich 45G 照片占大头)。首次全量后每日增量很小(实测一次增量 ~235 MiB)。**任何"文件陈旧/可删"判断一律以 `/mnt/user/...` 清单为准,缓存视图不算数**。事故链全文: `references/appdata-backup-source-cache-vs-user.md`。
- **SSD purchase deferred indefinitely** (prices surging): F: backup + daily sync is the safety net; SSD-death recovery = restore F: → array (12T free) → buy SSD whenever the price is right → mover back. GLOWAY smartctl PASSED at 3% life supports waiting.
- **openwrt config export DONE (2026-08-06)**: `F:/unraid-backup/istore-config-full.tar.gz` (30M — all 49 UCI config files + plugin data: passwall/openclash subscriptions, ddns, dropbear, samba4, lucky, ddnsto…). LuCI Web download was a DEAD END; the working route is **vdisk extraction** (qemu-img convert → read-only loop mount → overlay `upper/` tar) — see `references/openwrt-config-extraction.md`. F: final contents: `domains/openwrt` (11G) + `appdata` (390M) + `istore-config-full.tar.gz` (30M).

## openwrt (iStoreOS) config extraction — vdisk route (2026-08-06, WORKS)

Goal: grab the soft-router's config WITHOUT touching the running VM (soft-router must never be stopped; its SSH is closed; LuCI API download is auth-blocked). Full recipe + LuCI dead-end notes: `references/openwrt-config-extraction.md`.

```bash
# on the Unraid host
virsh dumpxml iStoreOS | grep 'source file'      # which disk(s) the VM uses
qemu-img convert -O raw /mnt/cache/domains/openwrt/istore_fixed.qcow2 /tmp/istore-current.raw
fdisk -l /tmp/istore-current.raw                  # find root partition (offset = start_sector * 512)
mount -o loop,ro,noload,offset=<start*512> /tmp/istore-current.raw /mnt/istore-ro
ls /mnt/istore-ro/                                # openwrt overlay root: upper/ + work/
ls /mnt/istore-ro/upper/etc/config/               # ALL UCI configs live here
tar -czf /tmp/istore-config-full.tar.gz -C /mnt/istore-ro/upper/etc .
umount /mnt/istore-ro; rm -f /tmp/istore-current.raw
# pull to F: with local rclone: rclone copy unraid:/tmp/istore-config-full.tar.gz "F:/unraid-backup/"
```

Key facts:
- `mount -o ro` FAILS on ext4 with a dirty journal → add `noload` (mount then shows `type ext4 (ro,...,norecovery)`).
- openwrt root = overlayfs: read-only squashfs (another partition) + writable `upper/` on ext4. Configs are in `upper/etc/config/`; `upper/etc` ≈ 65M, tar.gz ≈ 30M (includes plugin data). The overlay structure (`upper/`/`work/` + `.rootfs-uuid`) is what you see mounted — the configs are NOT at `/etc/` of the mount.
- qcow2 overlay chain (base + delta, e.g. `istore_fixed.20260511_Stable_Baseqcow2` + `istore_fixed.qcow2`) is handled transparently by `qemu-img convert`.
- iStoreOS network facts: VM name `iStoreOS`, MAC 52:54:00:f4:25:61 → 192.168.50.5 (find via `virsh dumpxml` MAC + `ip neigh`). **SSH IS available: dropbear 端口 64891, root，密钥免密（本机 `~/.ssh/id_ed25519` 公钥已写入 authorized_keys，2026-08-12）+ 密码 <见 gbrain concepts/net-topology>**；端口 22 是关的。LuCI on 80/443（WebUI 另走 Lucky 反代 :16601/ianlee168/）。
  ⚠️ **50.5 的访问凭证（SSH 端口/密钥/密码）、HA 备份密码、小米账号等都在 gbrain `concepts/net-topology` 页面（2026-08-12 用户批准存脑）—— 问用户要密码之前先查脑库！**（2026-08-14 用户亲训："昨天不是告诉你50.5的密码了吗？怎么又问"）

## passwall 国内延迟排查（2026-08-14 实测，全链路结论：系统正常）

症状：用户报"国内 ping 高、以前 2 位数"。完整诊断阶梯见 `references/passwall-domestic-latency.md`。要点：

- **50.5 SSH**: `ssh -p 64891 -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.50.5`（勿忘 -p 64891）。
- **实时配置**: `/etc/config/passwall`（uci show passwall | grep -E "tcp_proxy_mode|tcp_node|dns..."），运行态 sing-box 配置在 `/tmp/etc/passwall/acl/default/TCP_UDP_SOCKS.json`（route.rules 决定分流，看有没有 geoip:cn/ip_is_private direct 规则、final 兜底）。
- **nft 分流事实**（非猜测）：`nft list table inet passwall` → psw_chn（动态，2d TTL，按域名解析结果逐 IP 投喂）/ psw_chn_static（静态 chnroute CIDR，约 1335 段）/ PSW_NAT（TCP）/ PSW_MANGLE（UDP）链。关键规则都带 `meta mark != 0x50535731` 条件。
- **决定性验证 = 路由器上 tcpdump**：`tcpdump -i any -nn host <目标IP>`，从 .110 发连接，看 SYN 是 `pppoe-wan Out`（直连）还是进 127.0.0.1:1041（被代理）。
- **⚠️ /dev/tcp 计时是陷阱**：git-bash 里 `time bash -c "echo > /dev/tcp/IP/443"` 测的是**进程启动开销**（40-60ms 虚高），不是网络 RTT。用 `curl -w "%{time_connect}"` 或 tcpdump 才是真的。同理 ICMP ping 不走 passwall 重定向（只重定向 TCP/UDP），ping 正常 ≠ TCP 正常，反之亦然。
- 8/12 passwall 升级（26.7.1→26.8.12-r1，sing-box 1.13.18）"不动 /etc/config/passwall"，数据文件（chnroute/geosite/geoip）在升级时刷新。
- 本机 .110 实测：国内 TCP 直连 13-22ms、出口 IP=路由器 WAN（北京联通）、DNS 8ms —— 全正常；**若用户仍报高，先问"哪个设备/哪个目标/多少 ms"再继续**（可能是升级瞬间抖动或特定 IP 不在 chnroute）。

## go2rtc / Xiaomi camera stream — 401 expiry → restart + watchdog (2026-08-12)

> **先查 GitHub 共享仓库再动手**(2026-08-27 用户亲训:"你看看GitHub上面的skill")——多 bot 共管仓库 `github.com/ianlee168/hermes-skills` 的 `smart-home/go2rtc-camera/` 有 50.1 维护的官方修复流程,查完再决定要不要走下面的复杂流程;发现新坑后记得同步回该 skill(见 skill-github-mirror)。

Symptom: Frigate UI (`:5000`) loads but the camera shows no picture. **go2rtc container may be UP** — don't be fooled; its API port (yaml says 1985, container runtime log shows `[api] listen addr=:1986`) is not reachable from other hosts, so an HTTP 000 probe from outside is NORMAL, not a dead container.

Diagnosis on the Unraid host (`ssh root@192.168.50.1`):
- `docker logs --since 2m go2rtc | grep -c "401 Unauthorized"` — repeating 401s every ~10s = **Xiaomi P2P credential expired** (the `V1:...` token in the MOUNTED `/mnt/user/appdata/go2rtc/go2rtc.yaml`; the `/mnt/user0/` copy is a stale duplicate — see the split-brain section below). Total count `docker logs go2rtc | grep -c "401 Unauthorized"` (31,161 ≈ 3.6 days in the 2026-08-12 case).
- Fix: `docker restart go2rtc` — on startup it re-authenticates with the Xiaomi cloud (account credentials in go2rtc.yaml) and mints fresh P2P keys (`client_private`/`sign` appear in the dial log).
- Verify stream is actually delivering: `curl -s http://127.0.0.1:5000/api/stats` → camera entry `camera_fps` > 0 (python3 is absent on Unraid — read raw JSON, don't pipe to python3).

Watchdog (installed 2026-08-12): `/boot/custom/scripts/go2rtc-watchdog.sh` runs every minute via root crontab; restarts go2rtc if 401s appeared in the last 2 min; 5-min cooldown prevents double restarts; log at `/boot/custom/scripts/go2rtc-watchdog.log`. This is the standing fix for the recurring "没画面" complaint.

### 反复发作与新失败形态 (2026-08-27 实测)

- **401 不是 40 天周期**——实测间隔 4~7 天(8/12、8/20、8/27),watchdog 日志 `/boot/custom/scripts/go2rtc-watchdog.log` 记录每次触发;用户若问"多久一次",先查日志再答。
- **新形态:重启 go2rtc 也没用**。日志反复 `cs2: pop buffer is full` + `probe: miss: read media: ... i/o timeout`(TCP 能连上摄像头 192.168.50.66,但 P2P 媒体读不到)= **摄像头端 P2P 会话卡死**,不是凭据 401。排查顺序:
  1. `docker logs --since 6m go2rtc | grep -iE "xiaomi|401|i/o timeout|buffer"` 区分 401(凭据)vs i/o timeout(摄像头端会话)
  2. 先让用户**重启摄像头**(拔电 10 秒 / 米家 App),重置 P2P 会话
  3. 不行就**换凭据**(最终修法,2026-08-27 实测)。⚠️ **配置里直接放明文密码(`"<小米账号>": "<见 gbrain>"`)不够**——小米风控触发时照样 401。真正可靠的是 **WebUI 登录流程**:浏览器开 `http://192.168.50.1:1986` → add → Xiaomi → 填手机号+密码 → login → **弹短信验证码框(captcha + send 按钮),让用户在手机上收验证码,报给助手填入**(这一步 agent 只能点 send,验证码在用户手机;小米风控正是 401 深层原因)→ 登录成功后 **go2rtc 自动生成全新 V1 令牌并写回 go2rtc.yaml**。
- ⚠️ **PITFALL:WebUI 保存/登录会重写 go2rtc.yaml 并清空 `streams:` 节**(实测:登录后配置文件只剩 14 行,cw300 定义丢失 → 流全断,快照冻结)。**WebUI 操作前必须 `cp go2rtc.yaml go2rtc.yaml.bak-$(date +%Y%m%d-%H%M%S)`**,操作后核对 streams 节,丢了就从备份补回:
  ```yaml
  streams:
    cw300:
      - "xiaomi://<小米账号>:cn@192.168.50.66?did=1079924977&model=mxiang.camera.moc001&retries=60&timeout=30s"
  ```
  然后 `docker restart go2rtc`。注意 URL 里的 `&` 在 sed append 文本里无需转义,在替换串里要写成 `\&`。
- **验证要过硬(2026-08-27 教训,用户原话"修好的p啊")**:快照字节数相同 ≠ 恢复(冻结帧可能返回完全相同字节,51KB 两次一致是假象)。**唯一硬证据 = `curl -s http://127.0.0.1:1986/api/streams`**,producer 显示 `remote_addr: 192.168.50.66:<port>` + `bytes`/`packets` 持续增长 + 最近 2 分钟 401 计数为 0,才宣布恢复。
- **go2rtc 没有令牌生成子命令**:`go2rtc xiaomi --help` / `--help` 无该子命令,只会启动主程序并报 `listen ... address already in use`(端口被现有实例占用是正常输出,别误判)。
- 摄像头事实:小米 CW300,IP 192.168.50.66,did=1079924977,账号密码存 gbrain。
- ⚠️ **术语禁令**:描述摄像头接入一律说「go2rtc 流 / 视频流 / P2P」,禁止使用那个 R 开头的流协议缩写词(用户明令,任何上下文都不得出现)。

## Frigate 崩溃循环 — 容器层 SQLite 数据库损坏 (2026-08-27)

症状:frigate `Restarting (1)` 循环,WebUI 请求 HTTP 000;崩溃前日志 `peewee.DatabaseError: database disk image is malformed`。崩溃循环中 `docker exec` 全部失败(报 "Container ... is restarting")。

**关键事实(实测):frigate 的数据库在容器层 `/config/frigate.db`,不在宿主机。** 该容器只挂载了 `config.yaml` 单文件(`/mnt/user/appdata/frigate/config.yaml -> /config/config.yaml`)+ `storage -> /data`;宿主机 `/mnt/user/appdata/frigate/` 下的 `*.db` 是旧配置遗留(5 月日期),**改它们对容器无效**。动手前先 `docker inspect frigate --format "{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}"` 确认挂载,别被宿主机同名文件误导。

恢复流程(标准做法;`docker cp` 对 stopped 容器可用):
1. `docker stop frigate`(止住崩溃循环)
2. `docker cp frigate:/config/frigate.db /mnt/user/appdata/frigate/frigate.db.corrupt-<date>`(留证,可回滚)
3. 注入干净库:`docker cp <clean.db> frigate:/config/frigate.db`(干净库可用容器内 backup.db,或新生成空 sqlite;注意容器内备份库也在容器层,宿主机 8KB 的 backup.db 是旧遗留)
4. `docker start frigate` → 等 `health: healthy` → 验证 WebUI 和摄像头流恢复

代价:事件/检测记录清空(录像片段在 /data 不受影响)。数据库损坏不影响流本身——崩溃循环才是 WebUI 挂掉的原因。

- ⚠️ **WAL/SHM 陷阱(2026-08-27 实测)**:只替换 `frigate.db` 不够——容器层残留的旧 `frigate.db-wal`(实测 32MB、崩溃时刻的)与干净主库冲突,SQLite 报 `peewee.OperationalError: disk I/O error` 继续崩溃循环(注意是 disk I/O error 不是 malformed,别误判成磁盘满/可写层坏;`docker exec` 里 touch 文件成功 ≠ 数据库文件能写)。**必须三个文件一起清**:`frigate.db` + `frigate.db-wal` + `frigate.db-shm`,用 `docker cp` 空文件覆盖 wal/shm 即可(空 wal 文件 = 无 WAL,SQLite 正常打开;容器重启自动重建)。崩溃前残留的 wal 是"旧数据未合入新主库"冲突的根源。
- **崩溃循环里抓真实错误**:`docker logs --since Nm` 可能返回空(容器重启时间戳错乱),用 `docker start frigate` 后立刻 `docker logs --since 90s frigate | grep -B5 -A3 "Error|Traceback"` 抓到的是最新一次启动的报错;`docker logs frigate | tail` 可能停在几小时前的旧输出,别被误导。

## Docker 容器权限坑: SQLite CANTOPEN "out of memory (14)" (2026-08-31 实测)

症状: 容器崩溃循环 `Restarting (1)`,日志 `init app: unable to open database file: out of memory (14)` — **14 = SQLITE_CANTOPEN,是权限不是内存!** 容器以非 root 用户跑(Dockerfile `adduser -S`),bind mount 目录是宿主机 root 建的 → 写不进去。

修复:
```bash
docker run --rm --entrypoint sh <image> -c 'id <user>'   # 拿容器用户 uid:gid (例 yyb → 100:101)
chown -R 100:101 /mnt/user/appdata/<app>/data            # 宿主机上改属主
# 再 docker restart;健康后验证 docker logs 无 CANTOPEN
```

教训: 容器起不来先 `docker logs` 看真实报错;SQLite 报 14 优先怀疑挂载目录属主,别往内存/磁盘方向查。

## Unraid config-path split-brain — /mnt/user0 vs /mnt/user vs subdir copies (2026-08-12)

**Symptom:** you edit a config (or read one) and the container ignores it — the running app uses a completely different effective config.

- **Ground truth for what a container reads: `docker inspect <name> | grep -A8 '"Mounts"'`** — read the Source path from there, NOT from memory or topology notes.
- **`/mnt/user0/appdata/<app>/...` can be a STALE copy on this box**: `/mnt/user0/appdata/go2rtc/go2rtc.yaml` held an EXPIRED Xiaomi token while the mounted `/mnt/user/appdata/go2rtc/go2rtc.yaml` had the current one. Same trap: `frigate/config/config.yaml` (stale, port 8555) vs the REAL flat `/mnt/user/appdata/frigate/config.yaml` (port 8556). Unraid's merged (`/mnt/user`) vs cache-only (`/mnt/user0`) views + leftover subdir copies create two-version traps.
- **Effective-config check:** Frigate — `curl -s http://127.0.0.1:5000/api/config` (merged incl. defaults). go2rtc — runtime listen ports in `docker logs` (`[api] listen addr=:1986` ≠ what the yaml claims) or `docker exec go2rtc wget -qO- http://127.0.0.1:1986/api/streams`.
- **Rule:** when a container "ignores" your config edit, verify the mount source + effective config FIRST — don't keep editing the file you think it reads.

## Frigate detection: enable + object list (2026-08-12)

The "cat/person pops up a thumbnail" feature = Frigate detection events + snapshots, shown in the web UI at :5000.

- **`detect.enabled` must be EXPLICIT `enabled: true`** — omitting it left detection off (effective config `detect.enabled: false`, stats `detection_enabled: false`) despite `roles: [detect]`.
- **`objects.track` defaults to `[person]` only** — cats/dogs/birds never trigger events unless listed. Add `objects: track: [person, cat, dog, bird]`.
- Edit the FLAT `/mnt/user/appdata/frigate/config.yaml` (backup `cp ... .bak-YYYYMMDD`, scp the new file, `docker restart frigate`).
- Verify after restart: `curl -s http://127.0.0.1:5000/api/stats` → `detection_enabled: true` + `detection_fps > 0` (CPU detector ~16ms inference is fine); `/api/config` → `"track":["person","cat","dog","bird"]`.
- python3 is NOT installed on Unraid — read raw JSON (grep), don't pipe to python3.
- The "1 main + N small" grid layout only appears with multiple cameras; single camera = one live view, event thumbnails live in the review area.

## Unraid /boot FAT32 pitfalls (cron scripts on the flash)

- **/boot is vfat — NO exec bit.** `chmod +x` silently does nothing; executing a script directly fails `Permission denied` (exit 126). ALWAYS invoke `bash /boot/.../script.sh` — including in crontab lines.
- **Root crontab lives in RAM** (`/var/spool/cron/crontabs/root`) — lost on reboot. Persist by appending the re-add line to `/boot/config/go` (Unraid's startup script):
  `(crontab -l 2>/dev/null | grep -v <name>; echo "* * * * * bash /boot/custom/scripts/<name>.sh >/dev/null 2>&1") | crontab -`
- go2rtc container-internal API: `docker exec go2rtc wget -qO- http://127.0.0.1:1986/api/streams`.

## Unraid 仪表板时钟 24 小时制(2026-08-28 实测)

WebUI 顶部时钟格式由 `/boot/config/plugins/dynamix/dynamix.cfg` 的 `[display] date=` 控制。
默认 `date="%c"`(跟随 locale,zh_CN 下可能显示 12 小时制)。改显式 24 小时制**无需停阵列**,改完浏览器刷新即生效:

```bash
cp /boot/config/plugins/dynamix/dynamix.cfg /boot/config/plugins/dynamix/dynamix.cfg.bak-$(date +%Y%m%d)
sed -i 's/date="%c"/date="Y-m-d H:i"/' /boot/config/plugins/dynamix/dynamix.cfg
```

`[notify]` 段的 `time="H:i"` 本来就是 24 小时制,不用动。若用户报某处仍 12 小时制,多半是插件面板自己的显示,单独查。

## 单核长期高占用归因(「cpu4/cpu14 为啥一直高」)—— cputune 钉核链路(2026-09-08 实测)

症状:仪表板上某几个逻辑核长期高(cpu14 100%、cpu4 66%),其余核空闲。**先别在宿主机找进程——占用在 qemu 的 vCPU 线程里,元凶在 guest 内。**

```bash
# 1) 逐核 busy%(paste 后第二份字段是 $5/$6,写成 $4 会得到负数/天文数字)
awk '/^cpu[0-9]/{t=$2+$3+$4+$5+$6+$7+$8+$9;i=$5+$6;print $1,t,i}' /proc/stat > /tmp/c1; sleep 5
awk '/^cpu[0-9]/{t=$2+$3+$4+$5+$6+$7+$8+$9;i=$5+$6;print $1,t,i}' /proc/stat > /tmp/c2
paste /tmp/c1 /tmp/c2 | awk '{t=$5-$2;id=$6-$3;if(t<=0)t=1;printf "%s %5.1f%%\n",$1,(t-id)*100/t}'
# 2) 钉核映射
for v in iStoreOS "Home Assistant" Hermes; do echo "--- $v"; virsh dumpxml "$v" | grep -E "vcpupin"; done
# 3) 进 guest 找真凶:ssh ianlee168@192.168.50.161 → top / ps -eLo pid,tid,pcpu,comm --sort=-pcpu
```

坑:
- **`ps`/`top` 的 %CPU 是生命周期均值**,不是瞬时值;必须用 /proc/stat 或 /proc/<pid>/stat 两次采样求差(CLK_TCK=100)。
- **comm 含空格会字段错位**:解析 /proc/<pid>/stat 前先 `sub(/^[^(]*\(/,"")` + `sub(/^[^)]*\) /,"")` 再 split,否则 "CPU 0/KVM" 会把列整体右移、算出天文数字。
- 实测钉核(2026-09-08):**Hermes vcpu0→cpu4、vcpu1→cpu6、vcpu2→cpu12、vcpu3→cpu14**;iStoreOS→cpu2;HA→cpu1/cpu9。故 cpu4/cpu14 高 = 50.161 的 guest 在烧。
- 本次元凶:gbrain 升级后全量重嵌入——systemd-run 临时单元 `gbrain-embed-backfill.service`(`bun run src/cli.ts embed --all`,日志 /tmp/gbrain-embed-backfill.log)→ ollama `nomic-embed-text` 纯 CPU 嵌入(`OLLAMA_KEEP_ALIVE=-1`,runner 常驻但常驻不烧 CPU)。实测单请求 20s~2min、`GBRAIN_EMBED_CONCURRENCY=1`、约 1.26 分钟/页,936 页 ≈ 20 小时。
- 重建的是什么:gbrain 的 **chunk 文本 + 768 维向量索引**(pglite 的 content_chunks)。触发源是分块器版本 `SAFE_FENCE_CHUNKER_VERSION`(src/core/search/safe-chunks.ts,现为 4)在 v0.48.3.0 新建/提升 —— CHANGELOG 明写「Existing search chunks must be rebuilt with the corrected indexer before chunk-based remote retrieval resumes」;v0.48.5.0 的 CJK 分块重叠修复只对新切的块生效,所以重切块同时吃到该修复。重建期间 chunk 检索处于降级态,跑完恢复;本地 ollama 嵌入不花钱。
- 单独报错行 `the input length exceeds the context length` = 该块超过 **ollama 运行时上下文 2048**(不是模型上限 8192!看 `ollama ps` 的 CONTEXT 列),gbrain 默认 2000 token 分块会踩线 → 用 `GBRAIN_MAX_CHUNK_TOKENS=1200` 规避。
- **重嵌中途自杀的真凶 = 两个默认值(2026-09-08 实测)**:① `GBRAIN_AI_EMBED_TIMEOUT_MS` 默认 **60_000ms**(src/core/ai/gateway.ts),长邮件页一批 chunk 算不完 → 客户端 60s 掐断(ollama 日志 `400 | 1m0s | aborting embedding request due to client closing`)→ 重试 5 次 → 900s 零成功 → `stall watchdog` 杀掉整个 drain(日志写 "partial progress banked");② 上面的 2048 上下文。
  修法(纯 env,不改代码、不重启 ollama):`GBRAIN_AI_EMBED_TIMEOUT_MS=300000 GBRAIN_MAX_CHUNK_TOKENS=1200 GBRAIN_EMBED_CONCURRENCY=2 bun run src/cli.ts embed --all --catch-up`。改后实测 0 超时/0 上下文错/0 watchdog,单请求 1–3 分钟全 200。
- **常驻单元(2026-09-11 现状)**:50.161 跑的是 systemd 用户单元 `~/.config/systemd/user/gbrain-embed-backfill.service` → `bun run src/cli.ts embed --stale`(已带 `GBRAIN_EMBED_CONCURRENCY=1`、`GBRAIN_AI_EMBED_TIMEOUT_MS=600000`、`GBRAIN_EMBED_MAX_BATCH_TOKENS=1600`,`Restart=on-failure`/`RestartSec=30`)。它会因为超长 chunk 报 `input length exceeds the context length` 而非零退出 → **每 ~30 分钟自杀重启一次**(有进度但反复重扫)。顺带定位法:50.1 上 cpu4/cpu14 恒满 = Hermes VM 的 vcpu0/vcpu3(`virsh dumpxml Hermes | grep vcpupin`),不是主机进程。
- **给它加 `GBRAIN_MAX_CHUNK_TOKENS=1200` 是安全的(2026-09-11 实测)**:`resolveMaxChunkTokens()` 只决定**分块上限**(env → 模型 recipe `max_input_tokens`×0.6 → 默认 2000),而 `chunker_version` 是发布级常量(`SAFE_FENCE_CHUNKER_VERSION=4`),**不由 maxTokens 推导 → 不会触发全库重分块**;且 embed 命令自带 `healOversizedPageChunks()`(src/core/embed-oversize-heal.ts)—会把已有超长 chunk **切开再嵌**(日志 `split N oversized chunk(s) to fit embedding input limit`)。
- 验证姿势:`tail -60 ~/.hermes/logs/gbrain-embed-backfill.log | grep -aE "split|exceeds"` + `systemctl --user show gbrain-embed-backfill -p NRestarts`(不再增长 = 重启循环停了)。回滚:恢复单元 `.bak` + `daemon-reload` + `restart`。
- 停止/续跑:`pkill -f "cli[.]ts embed"`(**必须写成 `cli[.]ts`**——直接写 `cli.ts embed` 会匹配到自己的 ssh 命令行,把 ssh 连同旧任务一起杀掉,2026-09-08 踩过),之后用上面的 env 续跑(断点安全:runStale 只补 stale chunk)。查单请求耗时:`journalctl -u ollama-serve --no-pager | grep -oE '\| 200 \|[^|]+\|' | tail`。

## Unraid 插件盘点:版本核对法与三个必查项(2026-09-11 50.1 实测)

**版本核对不能靠 UI 或记忆**:逐个抓本机 `.plg` 的 `<!ENTITY version>` 与它的 `pluginURL` 指到的上游 `.plg` 比。`pluginURL` 里的 `&github;/&name;` 要按同名 ENTITY 展开;`dynamix.unraid.net` 走 `https://stable.dl.unraid.net/unraid-api/dynamix.unraid.net.plg`。

**"版本最新" ≠ "未过时"**:还要查上游仓库是否 `archived`(`curl -s https://api.github.com/repos/<owner>/<repo>` 看 `archived`/`pushed_at`)。本机三个过时项都是"版本号 == 上游最新,但上游已归档/换人":dcflachs/compose_plugin(已归档 → mstrhakr 继任,插件名不变)、scolcipitato/folder.view(已归档 → 后继 folder.view3,插件名变了,要重搭分组)、ich777/unraid-lxc-plugin(已归档,无后继)。

**"硬件驱动插件还需要吗"判定法(hwmon)**:`lsmod | grep -iE "it87|nct66"` + `dmesg | grep -i <mod>` + `/sys/class/hwmon/*/name` + 插件自己的 `dynamix.system.temp/drivers.conf`。本机 SuperIO = ITE **IT8613E**。判"驱动是否来自插件":比 md5 —— 插件 txz 里的 `it87.ko.xz` 与 `/lib/modules/<uname>/kernel/drivers/hwmon/it87.ko.xz` **完全一致**(df336de3…)才算在生效;而 `nct6687-driver` 是纯占位(模块躺在 `/lib/modules/<uname>/updates/`,从未加载、dmesg 0 条、hwmon 里没有)。`/boot/config/go` 里的 `modprobe it87 force_id=0x8620` 是老芯片强制绑定参数,**别删**。

**"这个插件在用吗"三查**:① `/boot/config/plugins/<name>/` 有没有 .cfg(只有 txz = 从没配置过,如 appdata.backup);② 功能痕迹(sensors.conf/drivers.conf、folder.view 的 docker.json、compose 的 projects/ 与容器 label、`/mnt/disks` 挂载);③ 卸载记录 `/boot/config/plugins-removed/*.plg`。

- **UD 挂的是 NTFS 时,`unassigned.devices-plus` 是多余的**:plus 只提供 exFAT/hfs+/apfs/parted + SMB/NFS/ISO 挂载;`samba_mount.cfg`/`iso_mount.cfg` 空 + 无 exFAT/apfs 设备 = 零使用。
- 已卸载插件的残留目录(`NerdTools/`、`buddybackup/`、`intel-gpu-top/` 的 0 字节 txz)只占 KB~百 KB 级,**flash 真大头是 `/boot/previous`(上一版 Unraid 整包,~1.1G,留着可回滚)**,别指望清插件目录腾空间。
- **别把备份的 .plg 留在 `/boot/config/plugins/`**:rc.local 的安装循环是 `for PLUGIN in $CONFIG/plugins/*.plg`(glob 不匹配 `.plg.bak-*`,但别赌) —— 挪到阵列 trash 区。

## dynamix.system.autofan 三个坑(2026-09-11 实测,50.1)

1. **它没有开机自启**。`.plg` 只在安装/点保存时用 `/tmp/start_service`(经 `at`)启动一次,`go` 里没有任何钩子 → **重启后守护进程消失,风扇曲线形同虚设**(配置还在,所以"看起来配好了")。判活:`pgrep -af "scripts/autofan -c"`(注意别被自己的 ssh 命令行匹配到)。控制命令:`bash /usr/local/emhttp/plugins/dynamix.system.autofan/scripts/rc.autofan start|stop|speed|restart`(只启 `service="1"` 的那些;多路风扇用 `dynamix.system.autofan<N>.cfg`,glob 是 `$plugin*.cfg` 所以 `.cfg.bak-*` 不会被 source)。
   修法 = 自建 `/boot/custom/scripts/autofan-boot.sh` 同时挂 go 与 cron:
   ```bash
   RC=/usr/local/emhttp/plugins/dynamix.system.autofan/scripts/rc.autofan
   running() { pgrep -f "$RC_DIR/autofan -c" >/dev/null 2>&1; }   # 用脚本全路径,避免匹配到自身/ssh
   running && exit 0
   for L in /var/run/autofan_*.pid; do P=$(head -1 "$L" 2>/dev/null); { [ -n "$P" ] && kill -0 "$P" 2>/dev/null; } || rm -f "$L"; done
   for i in $(seq 1 60); do [ -x "$RC" ] && break; sleep 5; done   # 开机早期 /usr/local/emhttp/plugins 可能没铺开
   bash "$RC" start; sleep 3; running || { rm -f /var/run/autofan_*.pid; bash "$RC" start; }
   ```
   go 里 `bash /boot/custom/scripts/autofan-boot.sh >/dev/null 2>&1 &`(带 `&`,别阻塞启动)+ 惯用 cron 重装行 `(crontab -l | grep -v autofan-boot; echo "*/5 * * * * bash /boot/custom/scripts/autofan-boot.sh >/dev/null 2>&1") | crontab -`(/boot 是 vfat,一律 `bash 脚本` 调用)。
2. **残留 lockfile → "起了又秒死"**。autofan 脚本里 `if [[ -f $lockfile ]]` 且 pid 已死 且未带 `-q` → 走 `else rm $lockfile` 分支 → 随后 `while [[ -f $lockfile ]]` 判定为假 → 后台循环**立即退出**(但 pid 已写进锁文件、syslog 也打了 "started")。症状:看护脚本报启动失败、`pgrep` 找不到进程、pwmN 却被动过(那是上一次的残留值)。**必须在启动前清掉指向已死 pid 的 `/var/run/autofan_*.pid` 并重试一次**;开机时 /var/run 干净,所以只有"中途死了再拉"才踩。
3. **`-f` 必须填与 `-c` 同通道的 tach**。实测 pwm3↔fan3(130→255 时 fan3 976→1506rpm,fan2 不动);填错虽仍能控速,但日志/rpm 报的是别的风扇,rpm_min 归零点也会打错通道。判定法:临时 `echo 1 > pwmN_enable; echo 255 > pwmN`,看哪个 `fan*_input` 变,完后 `echo <原值> > pwmN_enable` 还原(主板常默认 `pwmN_enable=2` = 芯片自动控速,此模式下写 pwmN 无效,autofan 需要时自己切成 1)。
4. 旁证:`sdspin /dev/nvme0` 返回非 0 → autofan 把 NVMe 当"读不到"**跳过** → 磁盘风扇曲线只由 HDD 驱动(实测 max 取自 sdb 45C,缓存盘 46C 不参与)。另外 `-l 30` 配内部 `PWM_OFF=PWM_LOW-PWM_OFF_OFFSET=0` 意味着"最热硬盘 ≤ TEMP_LOW 时风扇全停",要保底转速须把 `-l` 提到 ≥60。

## ca.update.applications:自动更新静默失效的根因(2026-09-11 实测)

`AutoUpdateSettings.json` 的 `cron.pluginCronFrequency` 是空字符串时,`include/exec.php` 的 `makeCron()` 走 default 分支,把字符串 `"Invalid frequency setting of "` 当 cron 表达式写进 `plugin_update.cron`,经 `/usr/local/sbin/update_cron` 合并进 `/etc/cron.d/root` → **那一行是无效的,自动更新永远不跑,而且没有任何报错**。合法值只有 `disabled|Daily|Weekly|Monthly|Custom`(`disabled` 时会删掉 cron 文件)。

```bash
grep -A1 "plugin autoupdates" /etc/cron.d/root          # 看到 Invalid 就是它
grep -n -A20 "function makeCron" /usr/local/emhttp/plugins/ca.update.applications/include/exec.php
# 改 AutoUpdateSettings.json 的 pluginCronFrequency(Monthly 还要 DayOfMonth/Hour/Minute),重写 plugin_update.cron,再:
/usr/local/sbin/update_cron        # 重新汇总各插件 *.cron 到 /etc/cron.d/root
```

⚠️ 别和 Unraid 自带的 `plugincheck`(dynamix.plugin.manager,`/etc/cron.d/root` 里每日 00:10)**搞混** —— 那个只负责"检查并提示有新版本",没坏;坏的是这个插件的"自动安装"。配置里还会残留早已卸载的插件项(本机 NerdTools.plg / dynamix.file.manager.plg),一并清掉。

## compose.manager 已被弃用 → Compose Manager Plus(2026-09-11 迁移实测)

`dcflachs/compose_plugin` **仓库已归档**(最后版本 2025.11.01),继任者 `mstrhakr/compose_plugin`,**插件名仍是 `compose.manager`** → 直接覆盖升级:

```bash
# 1) 先校验新版包能下且 MD5 对得上(pluginURL 里 packageURL 指向 GitHub release)
curl -sL <mstrhakr 的 plg> | grep -E "ENTITY (packageURL|packageMD5|version)"
# 2) 覆盖安装(下载到 /tmp/plugins;旧插件归档到 /boot/config/plugins-stale;失败丢 /boot/config/plugins-error)
/usr/local/sbin/plugin install https://raw.githubusercontent.com/mstrhakr/compose_plugin/main/compose.manager.plg
# 3) 验证
docker compose ls --all                      # 各栈仍在册
docker ps                                    # 容器没有被重启
ls /var/log/packages/ | grep compose         # 旧的 compose.manager-package-* 应已消失
```

- **安全前提(升级前必查)**:新版安装脚本只 `mkdir -p projects` + 清 `compose.manager-package-*` 遗留包条目,**不碰 `projects/*/docker-compose.yml`**;仍要 `cp compose.manager.plg compose.manager.plg.bak-<date>` 并确认 projects 内容。自带 compose CLI 在 `/usr/lib/docker/cli-plugins/docker-compose`(`docker compose version` 可验)。
- 迁移后它的自动更新会跟着新 pluginURL 走(若在 ca.update.applications 的列表里)。

## References

- `references/immich-update-script.md` — full bug chain + fixed script for the Immich updater (v3.0.3 → v3.1.0 case).
- `references/cache-and-cloud-backup.md` — dated cache/VM/docker inventory + R2 sizing math (2026-08-05).
- `references/wtr-pro-hardware.md` — WTR PRO motherboard/slot/disk inventory, no-parity finding, important-data tiers, SMART health sweep (2026-08-05).
- `references/rclone-gdrive-headless-oauth.md` — headless Google Drive OAuth on the server (5TB account), full interactive transcript + session state (2026-08-06).
- `references/automated-vm-backup-cron.md` — self-contained Hermes cronjob prompt + pre-flight checklist for the shutdown-window consistency backup (2026-08-06).
- `references/openwrt-config-extraction.md` — iStoreOS vdisk config extraction recipe + LuCI 2 (js) API auth dead-end transcript (2026-08-06).
- `references/vm-hung-diagnosis.md` — "VM running but unreachable" diagnostic ladder: ip neigh FAILED vs arp -n stale, port-timeout-vs-refused baseline, domstats CPU-advance test, destroy+start fix (2026-08-07).
- `references/haos-vm-image-mismatch.md` — HAOS VM "virtualized OS image is incorrect" warning: image-family cheat-sheet (generic vs ova), Unraid qcow2-overlay trap, release-asset check, official reinstall fix, HA docs raw-markdown fetch trick (2026-08-13).
- `references/passwall-domestic-latency.md` — "国内 ping 高"排查全记录：SSH 64891 访问、sing-box 运行态、nft 分流集合（psw_chn/psw_chn_static）、tcpdump 直连vs代理判读、/dev/tcp 计时陷阱 (2026-08-14)。
- `references/appdata-backup-source-cache-vs-user.md` — 备份源陷阱: `/mnt/cache` 缓存视图 vs `/mnt/user` 合并视图;2026-09-01 误判"陈旧文件"差点误删 481 个有效备份的完整链条、真实 appdata 构成(147G/40+容器)、隔离区三步清理法、待决策事项。
- `references/user-scripts-inventory.md` — user scripts 盘点/清理手册: 目录与 schedule.json 结构、2026-09-09 六个脚本逐个判定、mv 式可回滚清理法、悬挂条目/悬空镜像/明文凭据三坑。
- `references/rclone-backup-verify-and-cleanup.md` — rclone 备份三件事: 会让 rclone **永久挂起**的源类型(FIFO 命名管道等)与排除参数、逐文件校验"是否真同步"的方法、`.partial`/`.tmp-dl` 残留的删除前置校验 + 清单留证 + 释放量核对流程。
