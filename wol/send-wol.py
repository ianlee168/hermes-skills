#!/usr/bin/env python3
"""send-wol.py - wake 110me (50.110, Windows desktop) with a magic packet.

Use from 50.161 (161jie) when a task needs the GPU that only 50.110 has.
Stdlib only, no install needed:

    python3 send-wol.py                      # default target, default broadcast
    python3 send-wol.py BC:FC:E7:8C:3D:01    # explicit MAC
    python3 send-wol.py <mac> 192.168.50.255 # explicit broadcast

Log the printed timestamp: the boot time in 110me's report is matched against it
to prove the wake really came from this packet.

Verified hardware/firmware state on 50.110 (2026-09-22):
  * wired NIC: Realtek PCIe 2.5GbE, MAC BC:FC:E7:8C:3D:01, 2.5 Gbps, link up
  * adapter advanced props: Wake on Magic Packet = enabled, Wake on Pattern = enabled,
    Wake on LAN from shutdown (S5) = enabled
  * powercfg /devicequery wake_armed -> Realtek PCIe 2.5GbE Family Controller
  * AutoAdminLogon = 1 (user ianlee) -> boots unattended, Hermes gateway + laya-guard
    start by themselves, so the agent is live after a wake
  * open question: BIOS "Power On by PCIe/PCI" must be ON for S5 wake (cannot be
    read from the OS -> resolved only by a real wake test)
"""
import socket
import sys
import time

DEFAULT_MAC = "BC:FC:E7:8C:3D:01"
DEFAULT_BCAST = "192.168.50.255"


def main() -> int:
    mac = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MAC
    bcast = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_BCAST
    raw = bytes.fromhex(mac.replace(":", "").replace("-", "").replace(".", ""))
    if len(raw) != 6:
        print("bad MAC:", mac, file=sys.stderr)
        return 2

    packet = b"\xff" * 6 + raw * 16  # magic packet, 102 bytes
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for port in (9, 7):             # both usual WoL ports
        for _ in range(3):
            s.sendto(packet, (bcast, port))
            time.sleep(0.2)
    s.close()
    print("magic packet sent to {0} via {1} at {2}".format(
        mac, bcast, time.strftime("%Y-%m-%d %H:%M:%S")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
