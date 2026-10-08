# Automated shutdown-window VM backup via Hermes cronjob

Pattern established 2026-08-06 on the 50.1 Unraid + 50.110 Windows stack: schedule a one-shot
Hermes cronjob for a user-approved VM shutdown window; it stops the VMs, re-runs the incremental
rclone SFTP pull (so the vdisks are captured in a consistent state), verifies, restarts the VMs,
and reports back.

## Pre-flight checklist (before creating the job)

1. **Verify clocks BEFORE scheduling** — rclone log timestamps are **UTC**; the stack's local time
   is UTC+8. If you read an rclone `--stats` timestamp as local time you are 8h in the past and
   will happily schedule a job for an hour that already passed.
   ```bash
   date '+%Y-%m-%d %H:%M:%S %Z (%z)'                    # Windows host
   ssh root@192.168.50.1 "date '+%Y-%m-%d %H:%M:%S %Z (%z)'"   # server
   ```
2. After `cronjob action=create|update`, **read `next_run_at` in the response** — it must be a
   FUTURE local time. A one-shot job whose time already passed stays `state=scheduled`,
   `last_run_at=null`, and silently never fires.
3. **Set `deliver='origin'` explicitly** — in this session `deliver` defaulted to `local`
   (CLI/TUI session has no live channel) and the report would never have reached the chat.
4. Confirm the VM roster first: `virsh list --all`. On 50.1 the soft-router is **iStoreOS**
   (NOT the dir name `openwrt`) — it must never be stopped; `immort`/`opwrt` were already off.

## Self-contained cron prompt (works in a fresh session, no chat context)

```
执行 Unraid VM 一致性备份的停机窗口流程（一次性任务）。背景：Unraid 服务器（192.168.50.1）的
cache 数据已备份到 Windows 本机 F:/unraid-backup/（rclone remote 'unraid' = SFTP 到
root@192.168.50.1，密钥 C:/Users/<user>/.ssh/id_rsa，本机 rclone 在 PATH）。本任务在 VM 短暂
停机期间拿到干净一致的 vdisk 备份。

步骤：
1. SSH（ssh -o ConnectTimeout=8 root@192.168.50.1，免密）：virsh shutdown Hermes 和
   virsh shutdown "Home Assistant"（注意空格）。sleep 90 后用 virsh list --all 确认 shut off；
   仍 running 则 virsh destroy 强制关闭。绝对禁止对 iStoreOS（软路由）做任何操作。
2. 确认关闭后，本机后台运行增量拷贝：rclone copy unraid:/mnt/cache/domains
   "F:/unraid-backup/domains" --stats 30s -v（background=true + notify_on_complete=true），
   等待完成（最多 2 小时）。
3. 验证：rclone check unraid:/mnt/cache/domains "F:/unraid-backup/domains" --size-only，
   或对比 du -sh 两侧大小。
4. 重启 VM：virsh start Hermes 和 virsh start "Home Assistant"，virsh list --all 确认
   running；确认 iStoreOS 全程未被影响。
5. 中文汇报：F 盘备份总大小、增量拷贝耗时、rclone check 结果、三个 VM 最终状态。

安全红线（用户明确要求）：全程不得删除/移动/重命名任何文件（服务器和本机）。只允许拷贝、
VM 启停、读取。不清理任何旧备份。
```

## Why this exists

A plain full-tree `rclone copy` of `domains/` while VMs run never converges — the active vdisks
change every pass, so rclone re-copies them indefinitely ("hot copy", restore may need fsck).
Stopping the VMs makes the vdisks static; the re-run then produces a consistent backup in minutes.
This is the only way to get a clean vdisk set, and it must be scheduled in a window the user
approves (here: 03:00 local).

## Execution-time gotchas the job must survive

- SFTP copy of a running VM's qcow2/raw vdisk → each re-run re-transfers it; don't treat a high
  ETA as failure before the shutdown window.
- `rclone copy` resumes; an interrupted run (SSH blip) leaves a consistent partial tree — the next
  run just continues. Exit code 1073807364 (0x40010004-ish) seen on Windows = abnormal kill
  (SSH drop), not corruption; re-run to finish.
- qBittorrent `ipc-socket` → `SSH_FX_FAILURE` is normal; ignore.
- vdisk logical (sparse) size ≠ `du` usage: domains du'd 357G but transfers 664G. Target must fit
  the LOGICAL total.
