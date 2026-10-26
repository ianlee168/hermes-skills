# 意外重启取证：判「硬件复位 vs 软件重启」（AMD 平台）

用户报「自己重启了 / 以前三五个月都不重启」。**先定性，再谈版本回滚。**

## 1. 决定性证据：复位原因寄存器

内核在引导时读 AMD `FCH::PM::S5_RESET_STATUS`，把它打进 dmesg：

```bash
dmesg | grep "Previous system reset reason"
```

| 值 | 含义 | 结论 |
|---|---|---|
| `0x08000800` … `an uncorrected error caused a data fabric sync flood event` | CPU↔内存↔PCIe 互连出现不可纠正错误，硬件保护机制**立即复位整机** | **硬件级复位**，OS 没有任何机会写日志 |
| `0x00080800` … `software wrote 0x6 to reset control register 0xCF9` | 软件写复位寄存器 = 「重启」命令走的路径 | 正常重启 |
| `0x00200800` | 正常 ACPI 关机后开机 | 正常 |

**判据价值**：同一次故障如果反复出现，这个寄存器给出的是一串可对比的历史。若历史全是 `0x00080800`、只有最新一次是 `0x08000800`，那这次是这台机器第一次硬件级复位 —— 和「OS 升级引入回归」是两回事，回滚治不了。

## 2. 崩溃前日志：默认已丢，必须先开镜像

Unraid 的 `/var/log/syslog` 在 RAM 里，重启即失。**任何一次意外重启之后，第一动作是把这个洞补上**，否则下一次还是瞎的。

设置项 = Settings → Syslog Server → 「Mirror syslog to flash」，落到 `/boot/config/rsyslog.cfg` 的 `syslog_flash="1"`。命令行等价做法：

```bash
cat > /boot/config/rsyslog.cfg <<'EOF'
local_server=""
local_path=""
remote_server=""
remote_port="514"
remote_protocol="udp"
server_protocol="udp"
server_port="514"
server_folder=""
server_filename=""
log_rotation=""
log_size=""
log_files=""
syslog_flash="1"
syslog_shutdown_flash="1"
EOF
bash /usr/local/emhttp/plugins/dynamix/scripts/rsyslog_config   # 生成 /etc/rsyslog.conf 并回存 /boot/config/rsyslog.conf
/etc/rc.d/rc.rsyslogd restart
logger -t hermes-test "syslog mirror verification $(date)"
sleep 2; grep hermes-test /boot/logs/syslog        # 落盘才算成功
```

- 机制：`rsyslog_config` 往 `/etc/rsyslog.conf` 插 `$template flash,"/boot/logs/syslog"` + `*.debug ?flash`；**只改 rsyslog.conf 不写 rsyslog.cfg 会在重启后失效**。
- 历史回查：旧的 diagnostics 包 `ians-diagnostics-*.zip` 里有 `logs/syslog-previous.txt`（以及 `syslog.1/2.txt`），可以直接 grep 出「以前每次开机的复位原因」。
- 崩溃时刻定位：容器日志是 json-file、在 docker.img 里、**跨重启保留** → `docker logs --timestamps --since <T1> --until <T2> <container>` 找最后一条心跳（frigate 每分钟一条，能精确到 1 分钟）。新 boot 的 syslog 里 `emhttpd: unclean shutdown detected` = 非正常关机确认。

## 3. data fabric sync flood 的处置阶梯（不要先回滚 OS）

按代价从低到高，且**同时上无损的内核侧缓解**再观察：

1. **内核 cmdline（改 `/boot/syslinux/syslinux.cfg` 默认 label 的 `append` 行，先 `cp` 一份 `.bak-<date>`）**
   ```
   append initrd=/bzroot acpi_enforce_resources=lax processor.max_cstate=1 nvme_core.default_ps_max_latency_us=0 pcie_aspm=off
   ```
   | 参数 | 作用 |
   |---|---|
   | `processor.max_cstate=1` | 禁 CC6/最深 C-state（AMD 上公认的头号触发源），只留 POLL/C1 |
   | `nvme_core.default_ps_max_latency_us=0` | 关 NVMe APST；**DRAM-less 的 SM2263EN/XT 控制器是已知会引发 sync flood 的一类** |
   | `pcie_aspm=off` | 全局关 PCIe ASPM |
   
   代价：待机功耗/温度略升（低压 APU 几瓦级），换掉一整类竞态，值。
   **必须重启生效**；验证 `for s in /sys/devices/system/cpu/cpu0/cpuidle/state*/; do cat $s/name; done` 只剩 `POLL C1`。
2. **BIOS（Advanced → AMD CBS）**：`Power Supply Idle Control` → `Typical Current Idle`；`Global C-state Control` → `Disabled`；确认无 XMP/EXPO/超频。Unraid 官方社区对这种日志签名的标准建议就是这两条 + memtest。
   - ⚠️ **工控/小主机 OEM BIOS 菜单裁剪坑（WTR PRO 实测）**：天钡（TianBei / AOOSTAR）这类基于移动低压 APU（5825U）的主板，其 AMI BIOS 在 UI 呈现层**直接隐藏了 `Zen Common Options`**（只暴露了 `NBIO Common Options` 供改 IOMMU 和显存）。**进 BIOS 找不到 `Zen Common Options` / `Power Supply Idle Control` 属于正常现象，切勿让用户大海捞针**。因此，内核级 `processor.max_cstate=1` 才是最可靠的兜底，在 Linux 驱动层直接移除 C2/C3，效果与 BIOS 禁用完全等价。
3. **内存**：`dmidecode -t memory | grep -E "Size|Speed|Part Number"` —— **两条不同料号/不同厂商 ID 的模组混插是 fabric 错误的高危项**，也是版主第一个会问的问题。
4. **Memtest86+**：Unraid 启动菜单自带该项，32G 至少 2 轮（约一夜）。
5. **BIOS/AGESA 版本**：厂商官网常比出厂版新（本例 WTR PRO 5825U 出厂 0.22/2024-08，官方仓库已有 2025-02 版本）。AGESA 更新对 fabric 稳定性有直接影响，但要 U 盘 FAT32 根目录 + 开机 F7 刷写，有风险，先把流程给用户看再动手。
   - ⚠️ **外设实战要点（用户亲测铁律）**：**WTR PRO 刷机、引导选择与改 BIOS 压根用不到插鼠标，只插一个 USB 键盘即可**。方向键+回车+Esc+F4 搞定所有配置，不要多事让用户翻找/插拔鼠标。
6. **最后才做版本 A/B**：只有缓解无效时，才用 Tools → Update OS → Restore 回上一版做对照（`/boot/previous` 里就是上一版整包）。论坛上确有「升级后连续重启」的案例，但案例里的真凶最后是电源/节能设置，回滚并没有解决问题。

## 4. 编辑 syslinux.cfg 的坑

- 老配置里 `acpi_enforce_resources=lax` 可能**单独占一行**（不是跟在 `append` 后面）。用 `sed -i '<append行>s|.*|<新行>|'` 替换后，那行会变成一条悬空的不合法行 → 必须再删掉。改完 `cat` 全文核对每个 label。
- 只改默认 label（`label Unraid OS`）；GUI/Safe Mode 的 label 别动。

## 5. 开机复位取证钩子

`scripts/boot-reset-reason.sh` → 放 `/boot/custom/scripts/`，在 `/boot/config/go` 末尾加：

```
bash /boot/custom/scripts/boot-reset-reason.sh >/dev/null 2>&1 &
```

每次开机把复位原因 + 时间戳追加到 `/boot/logs/reset-history.log`（只留最近 300 行）。以后不用再翻诊断包猜；`/boot` 是 vfat，**一律 `bash 脚本` 调用，不能 chmod +x**。

## 6. 重启这台机的副作用

50.1 上跑着 iStoreOS 软路由 VM + 全部容器，重启 = **全屋断网 2–3 分钟**。内核参数要重启才生效时，先说清影响并约定时间窗口，不要默不作声重启。

## 参考

- Unraid 版主对同款日志的判定（硬件层、非 Unraid 崩溃）+ BIOS 建议：forums.unraid.net `Issues with Unraid server freezing up, seemingly randomly`
- 升级后连续重启但回滚无效、真凶是节能设置：forums.unraid.net `unRAID 7.3.3 stability issues`
- Zen3/4 sync flood 三项诱因（CC6 / DRAM-less NVMe APST / 核显 GFXOFF）与验证方法：GitHub gist `eliottness/ded6bce8163689dc426732d0670c7a28`
