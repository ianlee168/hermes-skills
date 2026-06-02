# `~/.hermes/skills/gbrain-backup/backup.sh` 的 set -e 陷阱

## 症状

每天 03:00 cron 跑 backup.sh，**功能层面完全成功**（archive + R2 上传 + Google Drive 上传 + verify 18 pages），但脚本最后 `exit 3`：

```
[2026-06-02 21:04:43] Deleted old backup: 2026-05-23 (gbrain_r2)
[2026-06-02 21:04:43] Deleted old backup: 2026-05-22 (gbrain_r2)
[2026-06-02 21:04:43] Deleted old backup: 2026-05-21 (gbrain_r2)
[2026-06-02 21:04:44] Deleted old backup: 2026-05-20 (gbrain_r2)
[2026-06-02 21:04:44] Deleted old backup: 2026-05-20 (gbrain_r2)
[2026-06-02 21:04:44] Cleaning old backups on hermes_backup (keep 7 days)...
                                            ← 停在这里，没 "done"
```

`echo $?` = 3。

## 根因

`# ---- 清理旧备份（各保留7天）----` 段原代码：

```bash
rclone lsl "${remote}:${dir}/" 2>/dev/null | \
    awk '/gbrain-.*\.tar\.gz/ {print $2, $4}' | sort -r | tail -n +8 | \
    while read name size; do
        rclone delete "${remote}:${dir}/${name}" 2>/dev/null && \
            log "Deleted old backup: ${name} (${remote})"
    done
```

问题：
- `rclone delete` 在 pipe-with-while 子 shell 里**偶发非 0 退出**（网络抖动、token 过期、文件正在被另一个 rclone 操作等）
- `set -e` + `rclone delete ... && log ...` 这种复合命令让非 0 退出立刻 terminate
- 整个清理段在两个 remote 上跑（R2 + Google Drive），第二个（GDrive）出问题会直接让整个脚本挂
- **R2 + GDrive 上传 + verify 都成功了**但 exit 3 → cron 监控/CI 会认为这次备份失败

## 修法

清理段本来就是 best-effort，**rclone delete 不应该让备份任务整体挂**。改成：

```bash
        while read name size; do
            rclone delete "${remote}:${dir}/${name}" 2>/dev/null || true
            log "Deleted old backup: ${name} (${remote})"
        done || true
```

两处加 `|| true`：
- 内层：`rclone delete` 失败不传播
- 外层：整个 while 段失败不传播

## 验证

跑完修复后：
```
exit code: 0 (期望 0)
elapsed: 113s
```

## 教训

**写带 `set -e` 的 bash 脚本，所有 best-effort 清理段必须用 `|| true` 包**。模板：

```bash
# 错误模式
rclone delete ... && log "deleted"

# 正确模式
rclone delete ... || true
log "deleted"
```

`set -e` + pipe-with-while + rclone 是雷区，下次写类似脚本直接 `|| true`。
