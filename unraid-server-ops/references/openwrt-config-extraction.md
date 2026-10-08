# iStoreOS (openwrt) config extraction from vdisk — 2026-08-06

Context: user wanted the soft-router's config backup on F: (Windows host). The soft-router
(iStoreOS VM on Unraid) must NEVER be stopped. This file documents the route that WORKED
(vdisk extraction on the Unraid host) and the LuCI Web-API route that did NOT.

## iStoreOS network/VM facts (verified)

| Fact | Value |
|---|---|
| VM name (virsh) | `iStoreOS` |
| Disk (virsh dumpxml) | `/mnt/cache/domains/openwrt/istore_fixed.20260511_Stable_Baseqcow2` (base) + `istore_fixed.qcow2` (overlay) |
| MAC | `52:54:00:f4:25:61` |
| IP | `192.168.50.5` (find: `virsh dumpxml iStoreOS | grep mac` → `ip neigh` on Unraid) |
| SSH | port 22 CLOSED (connection refused) |
| Web | 80/443 open (LuCI 2, iStoreOS theme) |

## WORKING route — extract config from the vdisk (no password, no VM stop)

```bash
ssh root@192.168.50.1
virsh dumpxml iStoreOS | grep 'source file'          # confirm which disks
qemu-img convert -O raw /mnt/cache/domains/openwrt/istore_fixed.qcow2 /tmp/istore-current.raw
fdisk -l /tmp/istore-current.raw                     # e.g. p1 128M, p2 256M, p3 2G "Linux filesystem"
mkdir -p /mnt/istore-ro
# root partition p3: offset = 786944 (start sector) * 512 = 402915328
mount -o loop,ro,noload,offset=402915328 /tmp/istore-current.raw /mnt/istore-ro
ls /mnt/istore-ro/           # overlay root: .rootfs-uuid, lost+found, upper/, work/
ls /mnt/istore-ro/upper/etc/config/    # ALL 49 UCI configs: network firewall dhcp passwall
                                       #   passwall_server openclash ddns dropbear samba4
                                       #   lucky ddnsto linkease naiveproxy microsocks ...
tar -czf /tmp/istore-config-full.tar.gz -C /mnt/istore-ro/upper/etc .
umount /mnt/istore-ro
rm -f /tmp/istore-current.raw
# from the Windows host:
rclone copy unraid:/tmp/istore-config-full.tar.gz "F:/unraid-backup/"
```

Result: `istore-config-full.tar.gz` = 30,186,829 bytes (~30M; upper/etc = 65M, upper/ total = 411M).

### Why it works / gotchas
- **`mount -o ro` fails** on ext4 with a dirty journal ("cannot mount ... read-only") → add `noload`;
  the mount then reports `type ext4 (ro,relatime,norecovery)`.
- **openwrt root is overlayfs**: the mounted partition is the writable upper layer, so the tree you
  see is `upper/` + `work/` — configs live at `upper/etc/config/`, NOT `/etc/` of the mount.
  Tarball `upper/etc` (not just `config/`) so plugin data (passwall/openclash node+subscription
  files, certs) is included.
- `qemu-img convert` transparently follows the qcow2 overlay chain (base + delta).
- The VM keeps running through all of this; qemu-img reads the qcow2 while QEMU writes it — fine
  for text configs (mtime/consistency risk negligible). Don't do this for a hot database disk.
- Unraid `/tmp` is tmpfs (RAM, 30G on this box) — big enough for a 2.4G raw image; use a disk
  path if the image is larger.

## DEAD END — LuCI 2 (js) API backup download

Attempted: download the standard backup via LuCI's API from curl. All variants returned the
login-page HTML (`<title>iStoreOS - LuCI</title>`, 13-93KB) instead of a tar.gz:

1. `POST /ubus` `session.login` with root creds → **works**, returns `ubus_rpc_session`
   (full ACL tree, `cgi-io.backup` read granted). So credentials were fine.
2. `GET /cgi-bin/luci/admin/system/flashops/backup?sessionid=<sess>` → login HTML.
3. `GET /cgi-bin/luci/;stok=<sess>/admin/system/flashops/backup` → login HTML (93KB full page).
4. `POST` variant of the same → login HTML.
5. cookie-jar dance (`-c` on `/cgi-bin/luci/`, then `-b` on ubus + download) → **LuCI 2 never
   sets an HTTP cookie** (empty jar); auth is ubus-session only, and the cgi-io download refused
   the raw sessionid param.

Don't burn time here — the vdisk route above is faster, needs no password, and returns MORE
data (the Web backup is only `/etc/config`-ish; the tarball includes plugin state).

## Leftover junk on F: (awaiting user OK to delete)

`F:/unraid-backup/openwrt-config-20260806.tar.gz` (18KB) — an HTML login page accidentally saved
with a `.tar.gz` name during the failed LuCI attempts. `file` reports "HTML document, ASCII
text". Harmless, but delete when the user nods.
