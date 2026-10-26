#!/bin/bash
# 每次开机记录「上次复位原因」——崩溃取证用（配合 /boot/logs/syslog 镜像）
# 部署：scp 到 /boot/custom/scripts/，并在 /boot/config/go 追加
#   bash /boot/custom/scripts/boot-reset-reason.sh >/dev/null 2>&1 &
# /boot 是 vfat 无 exec 位 —— 只能 `bash 脚本` 调用，别 chmod +x

OUT=/boot/logs/reset-history.log
mkdir -p /boot/logs
LINE=$(dmesg 2>/dev/null | grep -m1 "Previous system reset reason" | sed 's/^.*kernel: //')
BOOT=$(date "+%Y-%m-%d %H:%M:%S")
MARK="未识别"
case "$LINE" in
  *0x08000800*) MARK="【硬件级复位 → data fabric sync flood，内核来不及记日志】" ;;
  *0x00080800*) MARK="【软件复位 → 重启命令/正常重启】" ;;
  *0x00200800*) MARK="【正常 ACPI 关机后开机】" ;;
esac
printf '%s boot | %s | %s\n' "$BOOT" "${LINE:-<无复位原因记录>}" "$MARK" >> "$OUT"
tail -n 300 "$OUT" > "$OUT.tmp" 2>/dev/null && mv "$OUT.tmp" "$OUT"
exit 0
