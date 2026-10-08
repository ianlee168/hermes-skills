# CPU 80°C 高温排查全记录 — WTR PRO / Ryzen 7 5825U (2026-08-23)

场景:用户报 "50.1 温度都 80 了,室温才 27°"。

## 1. 定位 80°C 是谁的温度(先查证再答)

```bash
ssh root@192.168.50.1 'sensors; for z in /sys/class/hwmon/hwmon*/temp*_input; do echo "$z=$(cat $z)"; done; for d in /dev/sd?; do smartctl -A $d 2>/dev/null | grep -i temp; done'
```

实测关键输出:
- `k10temp-pci-00c3` → `MB Temp: +80.0 C` ← **80°C 来源 = CPU Tctl**(hwmon1 temp1_input=81250 mC)
- `amdgpu-pci-0400` → CPU Temp 73°C / PPT 15W(核显 edge 72°C,hwmon2)
- `it8613-isa-0a30`(hwmon3,SuperIO)→ temp1/temp2=41°C,temp3=80°C(≈CPU 附近 thermistor)
- NVMe Composite 45.9°C(crit 79.8)、硬盘 46-48°C → 全部正常

hwmon 映射: hwmon1=k10temp(Tctl)、hwmon2=amdgpu(edge)、hwmon3=it8613(SuperIO,风扇/电压)。
温度单位: sysfs 是 mC(毫摄氏度),`sensors` 是 °C。

## 2. 热源定位 = qemu 单核热点

```bash
uptime                                   # load 1.05 / 16 线程 → 整机不忙
top -bn1 | head -18                      # qemu-system-x86_64 PID 16921 占 61-67%
cat /proc/16921/cmdline | tr '\0' '\n' | grep -A1 '^-name'   # → guest=iStoreOS
virsh domstats iStoreOS --cpu-total      # cpu.time(ns) 两次采样间隔 2s 求 delta
virsh dumpxml iStoreOS | grep -c '<vcpu' # 2 vcpu
```

其他 qemu: PID 1962994=Home Assistant(~9%)、343503=Hermes(~4.5%)。

## 3. 软路由悖论(关键认知)

iStoreOS 内部(`ssh -p 64891 root@192.168.50.5`):load 0.22、CPU 90% idle、
sing-box/lucky/linkease 全部 0% —— **但宿主机 qemu 进程烧 67% 单核**。
原因: CPU 消耗在虚拟化层(virtio 网络事件循环;17 天累计 rx 337GB),不在客户机里。
**判 VM CPU 归属必须以宿主机 qemu 进程为准,guest 内部 top 不可信。**

## 4. 风扇探测(it8613 / hwmon3)

初始状态: pwm2_enable=1(manual)/pwm2=161 → fan2=4192 RPM(Array Fan,正常);
pwm3_enable=1/pwm3=102 → fan3=611 RPM(慢);pwm4_enable=2(auto)/pwm4=130 → fan4=0 RPM。

手动测试序列(测完必须恢复):

```bash
H=/sys/class/hwmon/hwmon3
echo 1 > $H/pwm4_enable; echo 255 > $H/pwm4; sleep 5; cat $H/fan4_input   # 仍 0 RPM → 该口无物理风扇/坏/线断
echo 1 > $H/pwm3_enable; echo 255 > $H/pwm3; sleep 8; cat $H/fan3_input   # 满速仅 1503 RPM
cat /sys/class/hwmon/hwmon1/temp1_input   # 81.2°C → 79.5°C,20s 后 80.75°C → 只降 1.7°C
# 恢复: echo 102 > $H/pwm3; echo 2 > $H/pwm4_enable
```

判读:
- **pwm4=255 满速仍 0 RPM** = 该口没有能转的风扇(空口/坏/测速线断)。
- **满速后 CPU 几乎不降温** = 风扇转速不是瓶颈 → 真正嫌疑:CPU 散热风扇没转(fan4 口)
  或散热器积灰/硅脂干涸 → **软件查到头,下一步必须开箱**。
- 风扇自动曲线 `pwmX_auto_point3_temp=80°C` = 设计上 80°C 才满速,80°C 属策略预期工作点
  (it8613 上 temp1=41°C 主板温度做温控源,CPU 80°C 时风扇不会加速 —— 又一个陷阱)。

## 5. 结论模板

80°C 是 CPU(k10temp Tctl),5825U Tjmax 95-105°C 内安全但偏热;成因 =
单核持续满载(iStoreOS qemu 的 virtio 网络开销)+ 小机箱散热余量 + fan4 口无风扇/散热器效率差。
处置优先级: ① 开箱查 CPU 散热风扇接线与积灰 ② 调风扇曲线(实测效果有限——**此结论已被 §6 更正:pwm2 有效,降 8°C**) ③ 限软路由流量。

## 6. 2026-09-08 更正:pwm2 才是压 CPU 温度的风扇,调它 −8°C

上一节的“风扇转速不是瓶颈 / 必须开箱”结论**错了一半**:那次只测了 pwm3(fan3 慢扇,满速仅 1503 RPM)和 pwm4(空口),
**没碰 pwm2**。而 pwm2→fan2 正是 Unraid dynamix.system.autofan 在控的那把扇。Unraid UI 把 fan2 标成
“Array Fan”(`/boot/config/plugins/dynamix.system.temp/sensors.conf` 里 `label fan2 "Array Fan"`),所以一直被当硬盘扇忽略。

实测(hwmon3,负载 2 核满载):

| pwm2 | fan2 | k10temp Tctl |
|---|---|---|
| 154 (60%) | 4041 RPM | 89.1°C |
| 220 (86%) | 5113 RPM | **80.9°C**(5min 稳定) |
| 255 (100%) | 5625 RPM | 81.5°C(75s) |

### 根因:autofan 插件只看硬盘温度,不看 CPU
autofan 脚本 v1.7 参数语义:**`-t` 低硬盘温度、`-T` 高硬盘温度、`-l` 最低 PWM 原始值(0-255)、`-m` 轮询分钟、`-e` 排除盘**。
旧配置 `-l 35 -t 30 -T 61` + 硬盘 41-47°C → PWM≈154(60%),CPU 89°C 插件完全不知道。
配置在 `/boot/config/plugins/dynamix.system.autofan/dynamix.system.autofan.cfg`(options 行是真实命令行,写在 flash 上重启仍生效)。

### 排查/操作顺序(下次直接照做)
1. `sensors` + 逐 hwmon 读 `fan*_input`/`pwm*`,并 `cat /boot/config/plugins/dynamix.system.temp/sensors.conf` 看 UI 标签——**别信标签,以实测温度响应为准**。
2. `ps -ef | grep "[a]utofan -c"` 看谁在控哪个 pwm、用什么曲线。
3. **手测前先 `rc.autofan stop`**(`/usr/local/emhttp/plugins/dynamix.system.autofan/scripts/rc.autofan stop|start`),否则插件 1 分钟内覆写 pwm,手测无效——8/23 那次就是被这个坑到,得出“调风扇没用”的错误结论。
4. 逐口 255 测转速 + 同步看 Tctl;测完恢复原值并 `rc.autofan start`。
5. 改曲线后验证:看 `ps -ef` 命令行是否更新,再等 2-5 分钟读 `fan2_input`/`temp1_input`。
6. fan4=0 RPM 仍是空口/坏口,与本问题无关。

### 6.1 正式方案(2026-09-08 已上线):CPU 温度曲线接管 pwm2
autofan 插件天生只看硬盘温度,无法按 CPU 调速 → 自制脚本接管 CPU 扇。

- 脚本 `/boot/custom/scripts/cpu-fan-curve.sh`(读 k10temp Tctl → 写 pwm2)
- 曲线: ≤45°C→70(27%) / 60°C→130 / 75°C→200 / 85°C→240 / ≥85°C→255
- 迟滞:升速立即(单次≤+60),降速需 target+15 < 当前且单次≤−25(防风扇忽快忽慢)
- 持久化:`/boot/config/go` 尾部加一行立即执行 + 一行 crontab `* * * * *`(本机既有的 go2rtc-watchdog 同套路)
- 插件侧:`dynamix.system.autofan.cfg` 的 `service="0"` 关掉 pwm2 那条,`rc.autofan stop|start` 重载;
pwm3(120mm 阵列风扇,满速仅~1500 RPM)仍由插件按硬盘温度管——**CPU 扇与硬盘扇是两把**
- 实测:满载 2 核时 Tctl 79-83°C / pwm2 216-232(85-91%) / fan2 ~5200 RPM;硬盘 40-47°C 未变
- 日志 `/var/log/cpu-fan-curve.log`(每分钟一行 Tctl/target/applied/fan2 RPM)
- 回退:cfg 里 service 改回 1 + 删掉 go 与 crontab 里的 cpu-fan-curve 行 + `rc.autofan start`
- 待观察:空闲时 pwm2 会降到 70(27%),若发现硬盘变热则抬高曲线地板

### 6.2 2026-09-08 A-B-A 实测:pwm3 那把扇对 CPU 温度没有可测影响

用户问「36% 那个风扇帮不上忙吗」。严格 A-B-A(CPU 扇冻结 pwm2=255/fan2≈5580 RPM 全程不变,pwm3 36%↔100% 来回切,各 4 分钟,真实负载 load 2.7-5.0):

| 阶段 | pwm3 | fan3 | Tctl 均值 |
|---|---|---|---|
| A1 | 93 (36%) | 551 RPM | 77.0°C |
| B | 255 (100%) | 1490 RPM | 75.9°C |
| A2 | 93 (36%) | 551 RPM | **73.9°C** |

36% 同时出现在最热(A1)与最凉(A2)两段 → 温度只是随负载缓慢下漂,与 pwm3 无关。
**结论:pwm3 帮不上 CPU 散热,别为它加噪音;让它继续按硬盘温度管硬盘。**(与 8/23 的 −1.7°C 观察一致)

坑:`rc.autofan stop` 会把**所有**已配置的 pwm 都写 255(包括 `service="0"` 的 pwm2)→ 想冻结 CPU 扇必须 stop 之后再写一次。

## 7. 夜间/持续高温归因:把风扇日志与作业时间轴对齐

用户报「凌晨那台机器风扇还在狂转」这类问题时,**唯一可靠的证据源就是自建曲线的日志**(比任何监控都好用):

```
/var/log/cpu-fan-curve.log     (root:root,每分钟一行)
2026-09-20 03:12:01 Tctl=94C target=236 applied=236 fan2=5625RPM
```

- 拉回本地(或 `ssh root@<nas> 'cat ...' > fan.log.txt`)后用脚本按 **10 分钟桶取均值+峰值**,再把同一时间轴的
  作业日志(`docker logs --since`、`journalctl`、cron/脚本日志)并排放 —— **重合即定罪**,不要靠猜。
- **基线必须自己先量**:本机(5825U)空闲+常驻容器(frigate 等 ~40% 单核)约 **62-66°C / ~4000 rpm**,
  所以 4000 rpm 是常态噪声;**持续 ≥88°C / ≥5600 rpm 才算异常**(≈2 核被长时间钉满)。
  把基线当故障、或把异常当基线,都会给出错的结论。
- **`/var/log` 是 tmpfs**:日志只覆盖最近几十小时(实测 2000 行 ≈ 33 小时),还会被截断/重建 →
  它只能证"最近这一两晚"。更早的夜要靠作业日志反推;**别因为"只有一晚数据"就否定用户的"连着几晚"体感**,
  改成明说"现有证据能证到哪一晚"。
- 夜间已知热源(本机):immich 00:00 媒体库扫描 + 02:00 数据库备份 + 03:0x checksum、Unraid 每日 cron 00:00、
  03:40 mover、以及 **VM 里的定时任务**(在 guest 里 `systemctl --user list-timers --all`,别只在宿主机找)。

**跨机归因的关键一问:干活的那台机器当时在不在线。** 本机的重活常常是"替另一台机器干活"
(例:嵌入算力本该走台式机 GPU,那台机器不在线就回退本机 CPU,慢 ~1700 倍 → 本机烧几小时)。
所以除了本机日志,还要查**对方机器的关机/休眠习惯**,Windows 侧一条命令列全:

```bash
Get-WinEvent -FilterHashtable @{LogName='System'; ID=1074,6006,6008,41} | Sort TimeCreated
# 1074 = 计划关机/重启(含触发者)、 6006 干净关机、 6008 非正常、 41 异常断电
```

和高温时段对一下就水落石出。**排期跨机算力前先看这个,别等出事再查。**

## 8. 短作业的长热尾巴 + 「候选作业清单」查法(2026-09-22 实测补充)

问题形态:用户报"连着几晚 2 点左右风扇狂转",而你已经修掉了当晚那个明显的大活(如 GPU 嵌入)——
**别停在你正在修的那个作业上**。实测那次点火的完全是另一条:VM 里 01:00 的自我备份
(zip 3 GB 单核压缩 + rclone 上传 2.9 GB),曲线 01:38→90°C、01:39→92°C / 5,672 rpm、01:40 回落。

- **归因前先列全候选作业**,再对齐时间轴(缺一项就可能全盘猜错):
  - 宿主机:`crontab -l` + `ls /boot/config/plugins/user.scripts/scripts/` + `/etc/cron.d/`
  - guest 内(本例 Hermes VM):每个用户的 `crontab -l` + `systemctl --user list-timers --all` + `systemctl list-timers --all`
  - 数据源那台机器(Windows 等):`schtasks /query /fo LIST /v` + Hermes cron
- **桶要开到 1 分钟**:自建曲线日志本身就是分钟粒度,而**短作业会留下很长的热尾巴**(曲线降速受迟滞限制、
  单次最多 −25)→ 1 分钟级尖峰在 10 分钟均值里被摊平,看均值会得出"没人干活却一直热"的错觉。
  正确做法:按 1 分钟找**起始上升沿**(那一刻就是作业开始),再看它持续多久。
- **压缩/上传类作业的 CPU 花在压缩上,按进程名列不出来**:`ps aux --sort=-%cpu` 的 %CPU 是生命周期均值
  (单核烧 90 秒的 zip 会显示成个位数)→ 必须两点采样求差:取 `/proc/<pid>/stat` 的 utime+stime(CLK_TCK=100)
  间隔 5-10s,`mpstat -P ALL 1 3` 看哪个核被钉满。锁定程序:`ls -l /proc/<pid>/exe`。
- 宿主侧对号:`virsh dumpxml <vm> | grep vcpupin` 把恒满的逻辑核映射回 VM,再进 guest 定位进程。
- 收尾口径:结论要写"哪条作业、几点到几点、峰值温度/rpm、为什么它慢/大"(本例:每天 2.9 GB 里 66% 是备份
  自己的日志),不是"风扇确实转了"。
