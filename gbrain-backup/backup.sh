#!/bin/bash
# gbrain-backup: 每日备份 gbrain-data 到 Cloudflare R2 + Google Drive（双备份）
set -e

BACKUP_DIR="/home/ianlee168/gbrain-data"
R2_REMOTE="gbrain_r2"
R2_BUCKET="huawei-car-raw"
GD_REMOTE="hermes_backup"
GD_DIR="hermes-gbrain-backup"
LOG_FILE="/home/ianlee168/.hermes/logs/gbrain-backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

mkdir -p "$(dirname "$LOG_FILE")"

# 检查 rclone remotes
for remote in "$R2_REMOTE" "$GD_REMOTE"; do
    if ! rclone listremotes 2>/dev/null | grep -q "^${remote}:"; then
        log "ERROR: remote '${remote}' not configured"
        exit 1
    fi
done

log "Starting gbrain backup (R2 + Google Drive)"

# 打包压缩
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="gbrain-${TIMESTAMP}.tar.gz"
TMP_ARCHIVE="/tmp/${BACKUP_NAME}"

log "Creating archive..."
cd "$(dirname "$BACKUP_DIR")"
tar -czf "$TMP_ARCHIVE" "$(basename "$BACKUP_DIR")"
ARCHIVE_SIZE=$(du -sh "$TMP_ARCHIVE" | cut -f1)
log "Archive created: ${BACKUP_NAME} (${ARCHIVE_SIZE})"

# ---- 上传到 R2 ----
log "Uploading to R2..."
rclone copyto "$TMP_ARCHIVE" "${R2_REMOTE}:${R2_BUCKET}/${BACKUP_NAME}" --log-file "$LOG_FILE"
log "R2 upload done: ${BACKUP_NAME}"

# ---- 上传到 Google Drive ----
log "Uploading to Google Drive..."
rclone copyto "$TMP_ARCHIVE" "${GD_REMOTE}:${GD_DIR}/${BACKUP_NAME}" --log-file "$LOG_FILE"
log "Google Drive upload done: ${BACKUP_NAME}"

# 记录最新备份名
echo "$BACKUP_NAME" > /tmp/latest_gbrain_backup.txt

# ---- 同步到 50.1 NAS 公网兜底（lucky 暴露的脑备份通道）----
# 任何 bot 失忆都能从公网 https://backup.techtreehole.com:16666/gbrain-latest.tar.gz 拉
NAS_HOST="${GBRAIN_NAS_HOST:-192.168.50.1}"  # 默认 50.1 Unraid，可被环境变量覆盖
NAS_PATH="${GBRAIN_NAS_PATH:-/mnt/user/NAS/gbrain-backup}"
NAS_FILE="${NAS_PATH}/gbrain-latest.tar.gz"
log "Syncing latest to NAS ${NAS_HOST}:${NAS_FILE}..."
if ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${NAS_HOST}" "test -d ${NAS_PATH}" 2>/dev/null; then
    if scp "${TMP_ARCHIVE}" "root@${NAS_HOST}:${NAS_FILE}" 2>>"$LOG_FILE"; then
        log "✅ Synced to NAS: ${NAS_FILE}"
    else
        log "⚠️ NAS scp failed (see scp error above) — backup still safe in R2 + Drive"
    fi
else
    log "⚠️ NAS ${NAS_HOST} unreachable or ${NAS_PATH} missing — backup still safe in R2 + Drive"
fi

# 清理本地压缩包
rm -f "$TMP_ARCHIVE"

# ---- 清理旧备份（各保留7天）----
for remote_spec in "${R2_REMOTE}:${R2_BUCKET}" "${GD_REMOTE}:${GD_DIR}"; do
    remote="${remote_spec%%:*}"
    dir="${remote_spec#*:}"
    log "Cleaning old backups on ${remote} (keep 7 days)..."
    rclone lsl "${remote}:${dir}/" 2>/dev/null | \
        awk '/gbrain-.*\.tar\.gz/ {print $2, $4}' | sort -r | tail -n +8 | \
        while read name size; do
            rclone delete "${remote}:${dir}/${name}" 2>/dev/null && \
                log "Deleted old backup: ${name} (${remote})"
        done
done

log "Backup finished: ${BACKUP_NAME} → R2 + Google Drive"

