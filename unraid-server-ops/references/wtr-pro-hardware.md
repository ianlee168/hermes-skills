# TianBei WTR PRO — hardware inventory (50.1, verified 2026-08-05)

Context: user feared cache-SSD death losing docker/VM data; asked whether a second
NVMe slot exists for raid1. All facts below from live SSH queries, not spec sheets.

## Board & BIOS

- Motherboard: **TianBei WTR PRO** (dmidecode baseboard: Manufacturer `TianBei`, Product `WTR PRO`)
- BIOS: AMI International, v0.22, 2024-08-02
- CPU: AMD Ryzen 7 **5825U** (Barcelo-U, 20 PCIe 3.0 lanes)

## Physical slots (dmidecode -t slot)

| Slot | Type | Data bus | Status (BIOS) | Reality |
|------|------|----------|---------------|---------|
| J3704 | M.2 Socket 3 | 2x/x2 (field unreliable) | Available | **ONLY standard NVMe SSD slot** — holds GLOWAY 1TB, runs PCIe 3.0 **x4 full speed** (LnkSta) |
| J3711 | M.2 Socket 1-SD | 1x/x1 | Available | Key A/E (WiFi-class) — empty; NVMe SSD will NOT fit |
| J3709 | M.2 Socket 1-SD | 1x/x1 | Available | Key A/E (WiFi-class) — empty; NVMe SSD will NOT fit |
| J3604 | PCI Express x8 (short) | x8 | Available | Empty — candidate for M.2→PCIe adapter (needs case-open check) |

Note: `Current Usage: Available` was reported for EVERY slot including the occupied
NVMe — BIOS field is not reliable.

## PCIe tree (lspci -tv)

- `00:01.3-[01]` → Intel I226-V (NIC #1)
- `00:02.1-[02]` → Intel I226-V (NIC #2)
- `00:02.4-[03]` → NVMe `03:00.0` (Silicon Motion SM2263EN — the GLOWAY)
- `00:08.1-[04]` → AMD SoC (Barcelo iGPU, USB 3.1 ×2, audio, PSP, Sensor Fusion Hub)
- `00:08.2-[05]` → 2× AMD FCH SATA AHCI

Only ONE NVMe endpoint exists → no second M.2 SSD slot populated or bridge-enabled.

## Disks (lsblk)

| Device | Model | Size | Role |
|--------|-------|------|------|
| sda | Cruzer Blade | 7.5G | Unraid boot USB |
| sdb | ST8000DM004 | 7.3T | Passthrough (Movie01 5T + TV03 2.3T) — NOT in array |
| sdc | WD80EZAZ | 7.3T | Array disk3 (`/mnt/disk3`) |
| sdd | TOSHIBA MG08ACA14TE | 12.7T | Array disk1 (`/mnt/disk1`) |
| sde | WD WUH721414ALE6L4 | 12.7T | Array disk2 (`/mnt/disk2`) |
| nvme0n1 | GLOWAY VAL1TNVMe-M.2/80 | 953.9G | Cache (btrfs, single device) |

- 4 SATA ports (ata1–ata4) ALL occupied — no free SATA bay for a cache-raid member.
- **Array has NO parity disk** (`mdNumDisks=3`, no parity device in mdcmd/lsblk) — all
  3 array disks are unprotected; a dead disk loses its data. 5 disk slots total (sbNumDisks=5).
- Cache: btrfs single-device pool (uuid `18a4d9a0-3be0-43eb-b556-5b292bd60a02`),
  954G total, ~585G used, ~365G free. `_snap_recover/` = 197G stale snapshot-recovery
  residue from 2026-05-09 (old copies of appdata 648M / domains 65G / system 131G / frigate 906M).

## Important-data classification on cache (what an SSD death costs)

| Tier | Path | Size | Loss |
|------|------|------|------|
| 🔴 must-backup | `domains/Hermes` (live VM) | 168G | irreplaceable |
| 🔴 must-backup | `domains/Home Assistant` (live VM) | 110G | irreplaceable |
| 🔴 must-backup | `domains/HAOS` + `domains/openwrt` | 9.3G | irreplaceable |
| 🔴 must-backup | `appdata/` (nodebb 306M, emby 65M, qinglong 15M, …) | 389M | configs/db gone |
| 🔴 must-backup | `system/libvirt.img` (VM definitions) | 1G | VM list gone |
| 🟡 rebuildable | `system/docker.img` | 130G | re-pull images (hours) |
| 🟡 disposable | `frigate/` | 906M | surveillance clips |
| 🟢 stale | `_snap_recover/` | 197G | delete with consent |

VM snapshot convention: `domains/<VM>.snapshot-YYYYMMDD-HHMMSS/` holds full sparse
`vdisk1.img` (provisioned size > real usage; use `du -sh` not `ls -la`).

## SMART health sweep (smartctl -a, 2026-08-05)

| Disk | SMART | Realloc | Power-on | Notes |
|------|-------|---------|----------|-------|
| GLOWAY 1TB (cache NVMe) | PASSED | — | 36,462h (4.2y) | 3% used, 71TB written, 0 media errors, 218 unsafe shutdowns, 46°C, **~25 DAYS cumulative over-temp warning** → M.2 slot runs hot; put a heatsink on the replacement disk |
| ST8000DM004 8TB (passthrough) | PASSED | 0 | 45,190h (5.2y) | 47°C |
| WD80EZAZ 8TB (disk3) | PASSED | 0 | 60,774h (**6.9y**) | oldest array disk; peaked 61°C |
| TOSHIBA MG08 14TB (disk1) | PASSED | 0 | 42,965h (4.9y) | 43°C |
| WD HC530 14TB (disk2) | PASSED | 0 | 49,972h (5.7y) | 47°C |

All disks healthy today but every array disk is a 5-7y 24×7 veteran AND the array has no
parity — none of them are safe from sudden death. The GLOWAY is fit to serve as an
offline cold spare after the swap (0 errors, 3% life used); its only flaw is heat.

## Backup options considered

- Cloud R2 (WSL `gbrain_r2:` → bucket `huawei-car-raw`): ~287G important ≈ $4.3/mo;
  71G snapshot-only ≈ $1.1/mo. Server rclone.conf is empty — credentials live in WSL.
- **Cloud Google Drive: user has 5TB → preferred, $0 incremental cost.** Server reaches
  Google directly. Headless OAuth procedure: `references/rclone-gdrive-headless-oauth.md`.
- Local: swap-to-larger-SSD (cold spare) or PCIe-adapter raid1 — one-shot cost, no monthly fee.
