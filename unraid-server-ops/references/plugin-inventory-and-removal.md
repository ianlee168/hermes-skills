# Unraid 插件:在用判定、卸载验证、原厂镜像对比

## 一、本机(50.1)插件判决表(右列即可复核依据)

| 插件 | 判决 | 复核依据 |
|---|---|---|
| it87-driver | **必须留** | 唯一硬件传感器/风扇控制来源:`/sys/class/hwmon/*/name` 里的 `it8613` 提供 fan2/fan3 真实 rpm、电压、板温;两个 pwm 通道都在这颗芯片(CPU 风扇曲线写 pwm2,硬盘风扇曲线写 pwm3)。在跑的 `it87.ko.xz` 与插件 txz 内文件 md5 一致(`df336de3…`),插件脚本用 `installpkg` 装它 |
| unassigned.devices | 必须留 | 两块 NTFS 盘挂在 `/mnt/disks/{Movie01,TV03}`(`mount` 显示 fuseblk = ntfs-3g,属 UD 本体) |
| dynamix.system.temp | 必须留 | `drivers.conf` = it87+k10temp;`nchan/system_temp` 进程在跑 |
| user.scripts / community.applications / folder.view / tips.and.tweaks / fix.common.problems / unbalanced / dynamix.unraid.net | 留 | 各有痕迹:脚本目录 / Apps / `docker.json` 里的 immich 分组 / `tips.and.tweaks.cfg` 的 `CPU_GOVERNOR=performance` / 按需工具 / Connect 本体(unraid-api) |
| dynamix.system.autofan | 修好保留 | 见 SKILL.md「dynamix.system.autofan 三个坑」 |
| nct6687-driver | 可删(本机已卸) | `modprobe nct6687` → `No such device`;SuperIO 是 ITE IT8613E,一块主板只有一颗主 SuperIO |
| unassigned.devices-plus | 可删 | 只提供 exFAT/hfs+/apfs/parted + SMB/NFS/ISO 挂载;`samba_mount.cfg`/`iso_mount.cfg` 空、无 exFAT/apfs 设备 = 零使用 |
| lxc | 可删 | 上游仓库已归档且无后继;`/mnt/user/lxc` 零容器 |
| appdata.backup | 可删 | 目录里只有 txz、没有任何 `.cfg` = 从没配置过(备份实际走 rclone→F:) |
| compose.manager | 已迁移 | dcflachs 版(仓库归档)→ mstrhakr「Compose Manager Plus」,插件名不变可覆盖升级 |
| folder.view | 待迁移 | 原仓库已归档,后继 folder.view3(插件名变了,分组要重搭) |

**残留目录的判据**:`/boot/config/plugins/<name>/` 还在、但 `/boot/config/plugins-removed/<name>.plg` 也在 = 该插件早已卸载,只剩残留目录(本机 NerdTools、buddybackup 就是这类;`intel-gpu-top` 连 removed 记录都没有,是安装没成)。这类目录只有 KB~百 KB 级 —— **卸载残留别指望腾空间,flash 真大头是 `/boot/previous`(上一版 Unraid 整包,~1.1G,留着可回滚)**。清理照红线:`mv` 到阵列 trash 区 → tar 打包留后路 → 用户确认后再 `rm -rf`。

## 二、判"这颗芯片在不在" —— 硬件驱动插件有没有用

1. `lsmod | grep -i <mod>` —— 现在在跑吗
2. **`modprobe <mod>` 是决定性一步**:`No such device` = 板子上没这颗芯片,插件永远无用;加载成功则看 `/sys/class/hwmon/*/name` 有没有多出新节点。安全:失败加载不影响已绑定的同类驱动(实测 it87/传感器读数不变)
3. 插件 txz 里的模块 vs `/lib/modules/$(uname -r)/...` 的 **md5** —— 一致才说明"现在跑的就是插件提供的那份"
4. 旁证:`dynamix.system.temp/drivers.conf`(用户勾选的传感器驱动,最能说明系统实际用哪颗芯片)、`/etc/modprobe.d/` 里的黑名单

⚠️ `dmesg | grep <mod>` 只覆盖本次开机,不能当"历史上从未加载"的证据。

## 三、只读挂原厂 OS 镜像做对比(`/boot/bz*`)

```bash
losetup -a                            # loop0=bzmodules, loop1=bzfirmware, loop2=docker.img, loop3=libvirt.img
cat /proc/mounts | grep -E "squashfs|overlay"   # bzmodules→/usr、bzfirmware→/lib/firmware,各自外面还套一层 overlay(upperdir 在 /var/local/overlay)
file /boot/bzroot /boot/bzmodules /boot/bzfirmware
mkdir -p /mnt/_x && mount -o ro /dev/loop0 /mnt/_x && ls /mnt/_x; umount /mnt/_x && rmdir /mnt/_x
```

- `bzmodules`(squashfs,挂 `/usr`)顶层就是 `/usr` 树(bin/lib/sbin/share/…),所以要找的文件路径写成 `/mnt/_x/lib/...`。
- `bzfirmware` = 纯固件(`/lib/firmware`);`bzroot` 是很小的 cpio(只有 microcode 几项)。
- **`bzmodules` 和 `bzfirmware` 里搜不到任何 `.ko.xz`**(全深度 find),而运行态 `/lib/modules` 在 rootfs(RAM)上有上千个模块(实测 1187 个)。所以**别再花时间从镜像里抠内核模块**;判"驱动是不是插件提供的"直接用第二节的 md5 对比。

### 三个假阴性(判断"原厂带不带 X"时全踩过)

1. **未压缩 cpio 不能用 `zcat`**:`zcat /boot/bzroot | cpio -t` → 0 条,以为"里面是空的"。`file` 先看格式(`bzroot` = `ASCII cpio archive (SVR4 with no CRC)`)→ 正确写法 `cpio -t < /boot/bzroot`。**通用姿势:先 `file`,再决定解包器。**
2. **链式 cpio 会早停**:`cpio -t` 只列出第一段(microcode 5~6 项)就碰到 `TRAILER!!!` 停下,后面内容**根本列不出来** —— 不能用"grep 不到"断言"原厂没有 X"。
3. **`find` 带 `-maxdepth` 会把"深度差一层"伪装成"不存在"**:`find /mnt/_x -maxdepth 6 -name it87.ko.xz` 为空,实际在深度 7(`lib/modules/<ver>/kernel/drivers/hwmon/`)。**查某个文件在不在,不要设 maxdepth。**

推广:任何"从镜像/备份里找文件"的判断,顺序都是「先把解包方式确认到能吃完整层 → 确认搜索深度不截断 → 最后才下结论」。
