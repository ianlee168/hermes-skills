# HAOS VM image-type mismatch → "虚拟化的操作系统映像不正确" (2026-08-13, 50.206)

## Symptom

HA Supervisor shows a daily warning banner:
`不支持的系统 - 虚拟化的操作系统映像不正确 · 由 Home Assistant Supervisor 报告`
(EN: "Unsupported system — Incorrect image for virtualization", unsupported reason code
`virtualization_image`).

## Root cause (verified on 50.206)

The HA VM's boot disk is a **bare-metal image** (`haos_generic-x86-64-13.0`) running
inside KVM. HAOS publishes a dedicated **virtualization line** (`haos_ova-*`) with
para-virtualization drivers + guest tools. os-agent/supervisor detects the mismatch and
marks the system unsupported.

Official docs (fetched from source):
> "Your Home Assistant OS installation appears to run in a virtualized environment using
> a disk image which is not meant to run in a virtualized environment."
> — `source/more-info/unsupported/virtualization_image.markdown` in home-assistant.io repo

## Diagnostic chain (what was run)

```bash
ssh root@192.168.50.1 "virsh list --all"                          # find the VM name
ssh root@192.168.50.1 "virsh dumpxml 'Home Assistant' | grep 'source file'"  # boot disk path
# → /mnt/cache/domains/HAOS/haos_generic-x86-64-13.0.S20260511175441qcow2
#   backing /mnt/cache/domains/HAOS/haos_generic-x86-64-13.0.img

# current HAOS release + asset names (2026-08-13: latest = 18.2)
curl -s https://api.github.com/repos/home-assistant/operating-system/releases/latest \
  | grep '"name"'
```

### Image family cheat-sheet

| Filename prefix | Family | Use |
|---|---|---|
| `haos_generic-x86-64-*` | bare metal | physical hardware ONLY |
| `haos_ova-*.qcow2.xz` | virtualization | **KVM/QEMU (this box's Unraid)** |
| `haos_ova-*.vmdk.zip` | virtualization | VMware/ESXi |
| `haos_ova-*.vhdx.zip` | virtualization | Hyper-V |
| `haos_ova-*.vdi.zip` | virtualization | VirtualBox |
| `haos_ova-*.ova` | virtualization | VMware/VirtualBox import container |

Note: the x86-64 `generic` line ships only `.img.xz` + `.raucb`; the KVM image is under
the `ova` line (`haos_ova-18.2.qcow2.xz`). aarch64 generic also gets `.qcow2.xz`.

## TRAP — Unraid's qcow2 overlay suffix is misleading

The VM's disk is named `haos_generic-x86-64-13.0.S<timestamp>qcow2` with a backing
`haos_generic-x86-64-13.0.img` (raw). That `.qcow2` is just **Unraid's copy-on-write
overlay on top of the base `.img`** — the FORMAT is qcow2, but the KERNEL inside is still
the generic bare-metal kernel. Do not conclude "it's a qcow2 so it's the KVM image";
format ≠ image family. Likewise, `qemu-img convert` cannot fix the mismatch — the kernel
is baked in.

## Impact

Cosmetic-to-moderate: orange banner + system status "unsupported" (Home Assistant offers
no support for it). Add-ons, automations, and HAOS OTA updates keep working. Many
installations live with it for months. Only reason to fix: get rid of the banner /
restore supported status.

## Official fix (no supported in-place path)

1. In HA UI: Settings → System → Backups → create a full backup, download the `.tar`.
2. Download `haos_ova-<latest>.qcow2.xz` on Unraid, `xz -d` to `.qcow2`.
3. Stop the VM, swap/create the VM disk to the ova image, boot.
4. During onboarding choose **Restore from backup**.
5. Re-attach any extra data disks (50.206 has `/mnt/user/domains/Home Assistant/vdisk2`,
   100G logical, snapshot from 2026-05-08) and redo any custom mount config.

Downtime ≈ 1h; also upgrades HAOS (50.206 was on 13.0 from 2026-05-11 → 18.2).

## Docs-fetching trick (HA docs pages are JS-heavy)

Rendered `home-assistant.io` pages embed a huge `window.__actions` JSON that drowns
`grep`/`sed` text extraction. Instead, fetch the **source markdown** straight from the
repo:

```bash
curl -sL https://raw.githubusercontent.com/home-assistant/home-assistant.io/current/source/more-info/unsupported/<reason>.markdown
# list all reason slugs:
curl -s https://api.github.com/repos/home-assistant/home-assistant.io/contents/source/more-info/unsupported | grep '"name"'
```

Reason slugs seen: apparmor, cgroup_version, connectivity_check, dbus, dns_server,
docker_configuration, docker_version, home_assistant_core_version, job_conditions, lxc,
network_manager, os, os_agent, os_version, restart_policy, software, supervisor_version,
system_architecture, systemd, systemd_journal, systemd_resolved, **virtualization_image**.
