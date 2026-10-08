# HAOS 在 Unraid/KVM 上换盘迁移(2026-08-13 实战,全部命令验证过)

适用场景:HA VM 用错镜像导致每天报「虚拟化的操作系统映像不正确」;或升级/迁移 HAOS。

## 0.5 只想改 HA 里的文件?先走 SMB,别停 VM

**HAOS 的 `/config` 通过 SMB(端口 445,Samba 插件,guest 可写)直接可读可写 —— 不用停 VM、不用 qemu-nbd:**

```bash
ls //<HA_IP>/config
cp local.yaml //<HA_IP>/config/www/
```

- 这才是**改仪表盘/模板/`www/` 里的图**的首选;qemu-nbd 挂盘(本文 §3)只在真要动镜像、分区时才用。
- 22222(SSH 插件)/1337(Code Server)/8099(File Editor) 默认都关着,445 是唯一入口。
- `net view \\<HA_IP>` 报 1702 是 RPC 的事,不代表共享不可用 —— 直接访问 UNC 路径验证。
- 动手前先建 `/config/.hermes-backup-YYYYMMDD/` 并把要覆盖的文件 `cp` 进去(存储盘上没有版本控制,这是唯一回退路径)。
- ⚠️ URL 前缀 `/local/xxx` 映射的是 **`/config/www/`**,不是 `/config/` 根目录:图放在根目录时
  URL **404 但文件确实在磁盘上**,只看 `ls` 会误判成"图没丢" —— 正确修法是把文件复制进 `www/`。

## 0. 诊断(先查证再答)

- `virsh dumpxml "Home Assistant" | grep "source file"` → 看启动盘文件名,`haos_generic-x86-64-*` = 裸金属镜像(装在 KVM 里必报 unsupported);`haos_ova-*` = 虚拟化专用。
- 官方原因页: https://www.home-assistant.io/more-info/unsupported/virtualization_image/
  (markdown 源在 home-assistant.io repo: `source/more-info/unsupported/virtualization_image.markdown`;用 curl 抓 raw.githubusercontent 可绕过浏览器)
- 最新版资产清单(确认 ova qcow2 文件名):
  `curl -s https://api.github.com/repos/home-assistant/operating-system/releases/latest | grep browser_download_url`
  → x86-64 虚拟化镜像在 **haos_ova** 系列(qcow2/KVM、vmdk/VMware、vhdx/Hyper-V、vdi/VirtualBox);generic 系列只有裸金属 .img。

## 1. 备份(HA 侧,必需)

- **2026-09-13 更新:已有 HA 长期令牌**(存 gbrain `credentials/home-assistant` + hermes .env),REST/WS 可读写;见 skill `home-assistant-api`。
- 当时(2026-08-13)无 HA token/SSH(本机 8123 只有 401,SSH 端口关),只能用户 UI 操作:设置→系统→备份→创建备份→下载 .tar。
- **备份可能加密**(创建时设的密码)——还原必输;密码存 gbrain。
- **文件名日期不可信**:`automatic_backup_2026_8_1.tar` 内部其实是当天 13:57 的备份。用 python tarfile 看内部 mtime 判定新鲜度。
- 备份内容扫描(判断某盘/设备是否被引用):python 解外层 tar,内层 gz 逐个 grep `/dev/sdX`、vdisk 等关键字。

## 2. 下载并准备新镜像(Unraid 上)

```bash
cd /mnt/cache/domains/HAOS
curl -sL --retry 3 -o haos_ova-18.2.qcow2.xz https://github.com/home-assistant/operating-system/releases/download/18.2/haos_ova-18.2.qcow2.xz
xz -t haos_ova-18.2.qcow2.xz && xz -dk haos_ova-18.2.qcow2.xz
qemu-img info haos_ova-18.2.qcow2   # 18.x 出厂已 32G 虚拟 / ~1G 实际,无需 resize 整个盘
```
下载约 511MB,Unraid 宽带 ~2 分钟;用 background=true + notify_on_complete 跑。

## 3. 扩 data 分区 + 注入备份(qemu-nbd)

出厂镜像里 hassos-data 分区只占 1.1G(32G 盘大半未分配),先扩再注入备份:

```bash
modprobe nbd && qemu-nbd --connect=/dev/nbd0 haos_ova-18.2.qcow2
blkid /dev/nbd0p*          # 找 hassos-data(ext4,通常 p8)
sgdisk -e /dev/nbd0        # GPT 未覆盖全盘 → parted resizepart 会报 "Unable to satisfy all constraints",先修 GPT
parted -s /dev/nbd0 resizepart 8 100%
e2fsck -f -y /dev/nbd0p8 && resize2fs /dev/nbd0p8
mkdir -p /mnt/ha-new && mount -o rw /dev/nbd0p8 /mnt/ha-new
mkdir -p /mnt/ha-new/supervisor/backups
cp <backup>.tar /mnt/ha-new/supervisor/backups/
sync && umount /mnt/ha-new && qemu-nbd --disconnect /dev/nbd0
```
注入后 onboarding 直接显示本地备份,免浏览器上传 686MB。

## 4. 停 VM + 换盘

```bash
virsh shutdown "Home Assistant"    # HAOS ACPI 极慢,实测 3-5 分钟;等 ~2 分钟不关就 virsh destroy(HAOS 扛断电)
virsh dumpxml "Home Assistant" > /root/HA-VM.xml.bak-YYYYMMDD   # 回滚保险
virsh dumpxml "Home Assistant" > /root/HA-VM-new.xml
sed -i "s|<旧盘qcow2路径>|<新盘qcow2路径>|" /root/HA-VM-new.xml
sed -i "/<backingStore type='file' index='4'>/,/<\/backingStore>/d" /root/HA-VM-new.xml   # 必须删 backingStore 块,否则 define 报错
virsh define /root/HA-VM-new.xml && virsh start "Home Assistant"
```
保留 MAC/网卡/vdisk2 不动 → 设备名尽量不变。注意:**新盘引导后 SATA 设备号会重排**(原 /dev/sdd 可能变 /dev/sdb),恢复的插件若绑定旧设备路径会找不到——用 PARTLABEL/UUID 识别而非设备号。

## 5. DHCP 绑定(iStoreOS)— 换盘后 IP 必漂!

全新 HAOS machine-id 变了 → DHCP DUID/client-id 变 → 路由器当新设备分配新 IP(实测 .206→.146)。修复:

```bash
ssh -p 64891 root@192.168.50.5    # iStoreOS,key 认证
cp /etc/config/dhcp /etc/config/dhcp.bak-YYYYMMDD
uci add dhcp host && uci set dhcp.@host[-1].name='home-assistant' \
  && uci set dhcp.@host[-1].ip='192.168.50.206' \
  && uci add_list dhcp.@host[-1].mac='52:54:00:cc:8b:ec'
uci commit dhcp && /etc/init.d/dnsmasq restart
# 然后 Unraid 侧 virsh destroy+start VM,拿回绑定 IP
```

## 6. 恢复 + 验证

- 用户浏览器 → onboarding → 恢复备份 → 选本地备份(注入的,免上传)→ 输入加密密码。
- 还原流程:先「下载最新核心」(~20 分钟)→ 还原(~45 分钟)→ 自动重启。
- 期间 `/api` 返回 **307**(更新页)→ **000**(核心切换)→ **401**(就绪)。
- 就绪判据:`curl -s -o /dev/null -w '%{http_code}' http://<ip>:8123/api/` = **401** 即实例带着原用户账户在跑。
- 用 `scripts/ha-ready-watch.sh` 后台监视(background=true + notify_on_complete),不用人盯。

## 7. 收尾

- 旧盘文件全保留(回滚);新 XML 备份在 /root/。
- gbrain concepts/net-topology 记录:新镜像路径、DHCP 绑定、备份密码、XML 备份位置。
- 通知用户操作时优先走微信(用户习惯看手机);im.bot 通道凭据在 gbrain credentials/api-keys。

## 陷阱清单

- **承诺停机时间前先量盘**:du -sh 实际占用 + 盘的位置(HDD 读 100G ≈ 12-15 分钟,nvme 秒级)。本会话先报"1-2 分钟"后修正为 15-20,被打脸。
- 备份文件名日期 ≠ 创建日期(看内部 mtime)。
- 旧 HA 的附加数据盘识别:PARTLABEL `hassos-data-external` + UUID 与内部 `hassos-data-old` 相同 = 迁移数据时的整盘拷贝,内容被备份覆盖后可安全处置(media 目录空 = 无独有用户文件)。
- 挂载运行中 VM 的盘:基盘因 COW 不被写,RO 挂载安全;overlay(.S*.qcow2)绝对不要碰。
- 删除任何盘/快照走安全模式:`mv` 到 timestamped 回收目录 → 观察数天 → 用户点头再 rm(用户 RED LINE)。
