# Unraid cache inventory & cloud backup sizing (as of 2026-08-05)

## /mnt/cache — nvme0n1p1, 954G total, 587G used, 365G free

| Dir | Contents | Size (du -sh) |
|---|---|---|
| `domains/` | VM vdisks + snapshot backups | 357G |
| ├ `Hermes` (live) | main VM | 168G |
| ├ `Home Assistant` (live) | VM | 110G |
| ├ `Hermes.snapshot-20260508-151352` | backup snapshot — 150G sparse `vdisk1.img` | 70G |
| ├ `HAOS` (live) | VM | 6.6G |
| ├ `openwrt` (live) | VM | 2.7G |
| └ `immort.snapshot-20260508-150924` | backup snapshot — 16G sparse `vdisk1.img` | 964M |
| `system/` | `docker.img` (139,586,437,120 B ≈ 130G) + `libvirt.img` (1G) | 131G |
| `appdata/` | docker configs: nodebb 306M, emby 65M, qinglong 15M, qbittorrent 3.1M, postgres 220K, go2rtc 4K | 389M |
| `frigate/` | surveillance recordings | 906M |

Snapshot dirs are FULL sparse vdisk copies, named `<VM>.snapshot-YYYYMMDD-HHMMSS/`.
Both snapshots dated 2026-05-08 — already 3 months stale at inventory time.
`_recovered/`, `_snap_recover/` also exist at cache root (Unraid recovery leftovers).

## Cloud upload path

- Server-local rclone: `/root/.config/rclone/rclone.conf` is **0 bytes** (no remotes on the Unraid box). `rclone` binary exists at `/usr/bin/rclone`.
- WSL on Windows host (50.110): `wsl -e bash -lc "rclone listremotes"` → only `gbrain_r2:`.
  - `rclone config show`: type=s3, endpoint `https://8bc8658cbb45f90275fd62d411b35723.r2.cloudflarestorage.com`
  - bucket: `huawei-car-raw`
- **`hermes_backup` (Google Drive) referenced by user's `gbrain-backup/backup.sh` is GONE from WSL config** — the script's remote-presence check (`rclone listremotes | grep`) now exits 1. Either re-add the GD remote or remove it from the script.
- User-owned skills that document this area (protected, need `hermes curator adopt` to edit): `~/.hermes/skills/cloudflare-access/` (R2 credential flow, Account ID 8bc8658cbb45f90275fd62d411b35723), `~/.hermes/skills/gbrain-backup/backup.sh`.

## R2 sizing math ($0.015/GB-month, 10GB free tier, free egress)

| Plan | Contents | Size | Cost/mo |
|---|---|---|---|
| A (recommended) | appdata 389M + 2 snapshots ~71G | ~71.4G | ≈ $1.1 |
| B | A + Hermes live VM (168G) | ~240G | ≈ $3.5 |
| C | full: domains 357G + docker.img 130G | ~487G | ≈ $7.2 |

Guidance: docker.img (130G) is the docker ENGINE image — do not back it up wholesale;
appdata (389M) holds the actual config/data and is trivially small.
