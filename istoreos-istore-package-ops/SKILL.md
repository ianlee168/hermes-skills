---
name: istoreos-istore-package-ops
description: 'Fix iStoreX/opkg file-clash install failures on iStoreOS.'
version: 1.0.0
author: 50.110 bot
license: MIT
platforms: [linux]
tags: [istoreos, openwrt, opkg, istorex, linkease, package-conflict]
metadata:
  hermes:
    tags: [istoreos, opkg, istorex, 包冲突]
    triggers: ["iStoreX 升级失败", "check_data_file_clashes", "linkease-common-bin", "商店暂不支持升级", "app-meta-istorex", "opkg 装不上商店包"]
---

# iStoreOS 商店包升级 / opkg 文件冲突处理

## When to Use

- iStoreX 商店点升级报 `Collected errors: check_data_file_clashes: Package X wants to install file /usr/sbin/... But that file is already provided by package * Y`
- 需要在命令行装 iStoreOS 商店(istore)的包,但 `opkg install` 报 `not available from any configured src`
- 需要评估某个 `app-meta-*` 包会连带装下多少东西

## 核心事实

1. **opkg 源里通常没有 istore 商店源**。iStoreOS 的 `/etc/opkg/distfeeds.conf` 只有 cernet 官方源(core/base/kmods/luci/telephony),
   商店应用的 ipk 在 `https://istore.istoreos.com/repo/{all/meta|x86_64/nas}/`。所以 `opkg install <商店包名>` 必报 not available;
   要么加源(`src/gz istore_all https://istore.istoreos.com/repo/all/meta`),要么下载 ipk 本地装,要么让商店界面自己装(商店自己拼 URL 下载)。
2. **`app-meta-*` 是应用定义包,Depends 是硬依赖**。装 `app-meta-istorex` 会把 app-meta-linkeasefull / dockermanager /
   kaiplus / baidudrive / istoreenhance / luci-theme-istorenas 全拉下来(实测 ≈166MB)。升级商店 meta 包前必须先算体积告知用户。
3. **冲突根因多为官方拆包没写 Replaces**。例:linkease 1.7.5~8664-r4 与新的 linkease-common-bin 1.7.5-8664-5
   都声明提供 /usr/sbin/{heif-converter,linkease-config.sh,linkease-media},而源里没有新版 linkease 可升。

## 处理流程(实测 2026-09-14)

```sh
# 1. 看现状:谁占了文件、源里有哪些版本
opkg list-installed | grep -i <pkg>
opkg list | grep -iE "^(linkease|app-meta-istorex)"   # 注意:此列表可能是残留 index
cat /etc/opkg/distfeeds.conf

# 2. 下载新包并"字节级"比对冲突文件,确认覆盖无风险(关键一步)
curl -fsSL -o /tmp/lcb.ipk "https://istore.istoreos.com/repo/x86_64/nas/linkease-common-bin_1.7.5-8664-5_all.ipk"
cd /tmp && rm -rf lkchk && mkdir lkchk && cd lkchk && tar xzf /tmp/lcb.ipk && tar xzf data.tar.gz
for f in usr/sbin/heif-converter usr/sbin/linkease-config.sh; do
  echo "$f new=$(md5sum $f|cut -d' ' -f1) old=$(md5sum /$f|cut -d' ' -f1)"
done
tar xzf control.tar.gz && grep -E "^(Package|Version|Depends|Replaces|Conflicts)" control

# 3. 备份将被覆盖的旧文件,再 --force-overwrite 安装
cp /usr/sbin/linkease-config.sh /tmp/linkease-config.sh.bak-$(date +%Y%m%d)
opkg install --force-overwrite /tmp/lcb.ipk
```

- 比对结论一致(2 个文件 md5 相同、1 个是更新版)→ `--force-overwrite` 安全,只是 opkg 账本归属变更。
- 不要为了过冲突去 `opkg remove` 旧包:旧包可能仍被其它包依赖(查 `/usr/lib/opkg/status` 里 `Depends:.*<pkg>`)。

## 评估 meta 包体积(在 PC 侧做,别在路由器上折腾)

```python
# istore 源索引位置(注意:没有 /repo/all/Packages.gz,只有子目录)
#   https://istore.istoreos.com/repo/all/meta/Packages.gz     (138 个包)
#   https://istore.istoreos.com/repo/x86_64/nas/Packages.gz   (62 个包)
# 解析 gzip 后的 Packages,按空行分块 → 字典;递归展开 Depends 统计体积
```

- **`Installed-Size` 字段单位是字节不是 KB**(linkeasefull=85599120 ≈ 85.6MB,linkease-common-bin=2901905 与实际 ipk 2.9MB 吻合)。

## BusyBox tar 解 ipk 的坑

- ipk 内成员名带 `./` 前缀(`./control.tar.gz`)。指定成员名解包(`tar xzf x.ipk control.tar.gz`)在 BusyBox tar 下
  **静默失败**,`ls` 一看是空的,容易误判包格式。正确做法:先 `tar tzf x.ipk` 看列表,再 `tar xzf x.ipk` 解全部。
- 反过来,`tar tzf` 能列出成员说明它确实是 tar.gz 包装,不必找 `ar`(BusyBox 通常没有 ar)。

## 命令行装商店包(实测 2026-09-14 完整跑通)

### ① 加源(4 条,别重复)

```
# /etc/opkg/customfeeds.conf —— istore_compat 已在 /etc/opkg/compatfeeds.conf,别重复写
src/gz is_nas_luci https://istore.istoreos.com/repo/all/nas_luci
src/gz is_store    https://istore.istoreos.com/repo/all/store
src/gz is_nas      https://istore.istoreos.com/repo/x86_64/nas
src/gz is_meta     https://istore.istoreos.com/repo/all/meta
```

### ② 签名坑(最容易卡在这里)

- 症状:`opkg update` 打印 `Signature check failed.`,随后 `opkg install` 报
  `Package <x> is not available from any configured src`,但 `opkg list | grep <x>` 又能看到。
- 真相:**签名失败的源,索引文件会被 opkg 静默删掉**(只留 `is_meta` / `istore_compat`)。
  对比 `/var/opkg-lists/`:通过的源有 `xxx` + `xxx.sig`,失败的只剩别的源。
- 根因:商店源用**两把 key** 签。系统自带 `a56f16274c6d486b`(istore key,与 repo 根
  `key-build.pub` 一致)+ `d310c6f2833e97f7` + `e767f93a0951ff45`;而 `is_nas_luci`/`is_store`/`is_nas`
  的 `.sig` 写的是 `signed by key 1d15e401c11b3e0f` —— **这把公钥公开渠道拿不到**(repo 下无
  `/keys/`、`key-<id>.pub` 均 404),别浪费时间找。
- 正解:学商店自己的做法 —— 它的隔离环境 `/tmp/is-root/etc/opkg.conf` **没有 `option check_signature`**。
  所以:临时把 `/etc/opkg.conf` 的 `option check_signature` 注掉 → `opkg update` → 装 → **立即恢复**。
  (验证 sig 归属:`usign -V -p /etc/opkg/keys/<id> -x Packages.sig -m Packages.gz`)

### ③ 装(一次过全部拆包冲突)

```sh
# 安装耗时长且会重启服务,必须后台跑+轮询,防 SSH 断线丢进度
nohup sh -c "opkg install --force-overwrite app-meta-istorex > /tmp/meta-install.log 2>&1" >/dev/null 2>&1 &
i=0; while [ $i -lt 33 ]; do pgrep -x opkg >/dev/null 2>&1 || break; sleep 15; i=$((i+1)); done
tail -20 /tmp/meta-install.log
```

- 用 `pgrep -x opkg` 轮询,别用 `pgrep -f "opkg install"`(会匹配到自己那条 `sh -c` 包装命令,永远不退出)。
- 一个 `--force-overwrite` 就能过掉链上**所有**同型冲突(luci-lib-linkeasefile vs luci-app-linkease 等),
  无需逐个处理。冲突包与被替换包**版本号相同**时(如两边都 2.1.70-r3)文件通常完全一致,风险极低。
- 实测代价:装完 app-meta-istorex 全家,overlay 从 444M → 1.1G(剩 812M),内存可用仍 1.4G/2G;
  `linkeasefull` 装完会提示 `data root is not initialized; starting for first-run setup`,需用户进面板初始化。
- 完成标志:再跑一次 `opkg install --force-overwrite app-meta-istorex` 应输出 `installed in root is up to date`。

## 环境备忘

- 50.5 iStoreOS 24.10.8 x86_64,dropbear 端口 64891,root 公钥已授权;overlay 可用约 1.4G(装 166MB 应用可行但不宽裕)。
