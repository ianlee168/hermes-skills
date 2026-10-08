# VM hung-guest diagnosis — full transcript & output interpretation (2026-08-07)

Case: Unraid VM "Hermes" (192.168.50.161) unreachable from Windows host 50.110.
`ssh ianlee168@192.168.50.161` → `Connection timed out`. libvirt said `running`.
Root cause: guest OS hung (kernel network stack dead, CPU still spinning). Fixed with
`virsh destroy` + `virsh start`. Hermes gateway auto-restored via systemd user service.

## Windows-host side (first signals)

```bash
ping -n 4 192.168.50.161
# Reply from 192.168.50.110: Destination host unreachable   ← .110 is the LOCAL machine
# 100% loss. "Reply from <own-ip>: Destination host unreachable" = no ARP resolution.
# The target is not on L2 at all (off, wrong subnet, or dead stack).
```

Populate the ARP table with a sequential sweep (Hermes terminal gatekeeper rejects
`&`-parallel loops — no `ping ... &`):
```bash
for i in $(seq 1 254); do ping -n 1 -w 300 192.168.50.$i >/dev/null 2>&1; done
arp -a    # DON'T pipe through sort — Windows GBK locale output breaks sort multibyte.
```
Missing from sweep + no ARP entry = host not on the LAN.

## Unraid-host side (the decisive checks)

```bash
virsh list --all
# 1  iStoreOS    running
# 2  Hermes      running        ← VM process alive, guest may still be dead
# 3  Home Assistant  running    ← name has a space; quote names in shell loops

virsh domifaddr Hermes           # EMPTY — no guest agent installed; useless here
virsh domiflist Hermes
# vnet1  bridge  br0  virtio-net  52:54:00:25:00:a5

arp -a | grep -i 52:54:00
# ? (192.168.50.161) at 52:54:00:25:00:a5 [ether] on br0
# ← hypervisor bridge STILL sees the VM at .161 (entry persists for dead guests too)

ping -c 4 -W 2 192.168.50.161     # from the host: 100% loss → guest not answering
ip neigh show | grep 50\.161
# 192.168.50.161 dev br0 FAILED   ← kernel probed, no ARP answer = DEAD.
# (earlier `arp -n` still showed a "C" entry — stale; trust `ip neigh` state, not arp -n)

timeout 3 bash -c "</dev/tcp/192.168.50.161/22" && echo OPEN || echo CLOSED
# timeout → dead. Baseline: same probe on .206 → "Connection refused" (alive, no SSH).
# The timeout-vs-refused contrast is the single most informative 3-second test.

virsh domstats Hermes --cpu-total | grep cpu.time; sleep 3; virsh domstats Hermes --cpu-total | grep cpu.time
# 20716475639000 → 20719524448000 ns  (+1.0s CPU / 3s wall)
# CPU advancing + network dead = kernel hung (soft lockup / D-state storm), NOT frozen vCPU.
```

## Fix

```bash
virsh reboot Hermes        # "Domain 'Hermes' is being rebooted" — but hung guest can't
                           # process ACPI; after 45s still `running`, ping still dead.
virsh destroy Hermes && sleep 3 && virsh start Hermes   # power-cycle (consent required)
# Hermes reboots in seconds; ping UP on first retry.
```

Verify: `ssh ianlee168@192.168.50.161 'hostname; uptime'` → `hermes`, then
`systemctl --user is-active hermes-gateway` → `active` (service auto-starts; enabled).

## Post-mortem

- Disk was 50% (119G free) — disk-full theory ruled out; hang cause never confirmed
  (reboot wiped kernel logs, no passwordless sudo for `journalctl -b -1`).
- Disk-full is still the #1 suspect class for this symptom — check `df -h` in the guest
  when possible.
- VM runs Ubuntu with NO guest agent: `virsh domifaddr`/`domstate` can't see inside.
  Ping/ARP probing is the only liveness check.
