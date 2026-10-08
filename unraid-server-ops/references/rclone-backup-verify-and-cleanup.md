# rclone 备份: 挂死源、校验与残留清理

适用: 用 rclone(SFTP/本地)从 Unraid 往本机 F 盘做增量备份时, 任务"跑不完"、"像是卡住"、
以及备份目录里出现 `.partial`/`.tmp-dl` 残留要不要清理。

## 一、会让 rclone 永久挂起的源(无报错, `--ignore-errors` 无效)

| 源类型 | 症状 | 处置 |
|---|---|---|
| FIFO 命名管道(如 netdata `cache/.netdata_*_fifo`) | 读无 EOF → 永久停在 `Transferring`;统计已 `Transferred 100%` 后再无进展 | `--exclude "**/*_fifo"`(必要时再加精确路径 `--exclude "/netdata/cache/**"`) |
| 运行中容器的 unix socket(如 qbittorrent `ipc-socket`) | `SSH_FX_FAILURE` 报错, 很快失败不挂 | `--ignore-errors` 即可 |
| 悬空软链接(roonserver、nodebb 插件目录等) | `Open failed: file does not exist`, 很快失败 | 同样忽略 |
| 活跃写入的大文件(运行中 VM 的 qcow2 磁盘) | mtime 持续刷新 → 每日判为重传, 且在本机收尾改名环节可能被 Defender 扫描卡死 | 明确排除该文件, 改走 `scp -p` 直写(无改名环节) |

判断某一路径是不是 FIFO: `ssh root@<host> "stat -c '%F' <path>"` → 返回 `fifo` 就别让 rclone 去读它。

**收尾口诀**: 若 stats 显示 `Transferred 100%` 且只剩某个对象停在 `Transferring`, 先怀疑 FIFO/socket,
而不是继续等 —— 要么加 `--exclude` 重跑, 要么结束进程:
`powershell -NoProfile -Command "Stop-Process -Name rclone -Force"`。
⚠️ git-bash 里 `taskkill //F //IM rclone.exe` 会被 MSYS 改写参数、报"无效参数", 别用。

**收益量级**: 一个 40+ 容器 / ~147G 的 appdata 树, 加 FIFO 排除后从 ~30 分钟(实际全是干等)降到 ~2 分钟。
任务时长直接决定它会不会被重启 drain / 关机窗口腰斩, 所以这个排除同时是稳定性修复。

## 二、校验"备份是否真的同步了"(逐文件, 别只看总数)

`rclone size`、`du -sh` 受稀疏文件与视图影响, 单独不能作证据。做法: 两侧各取 `{文件名: 大小}` 字典再比差集。

```python
remote_raw = subprocess.run(["rclone", "lsl", "unraid:/mnt/user/appdata"],
                            capture_output=True, timeout=180).stdout.decode("utf-8", "replace")
# local 侧用 os.scandir 逐文件取 st_size
```

⚠️ **不要用 MSYS 的 `find` + `-printf` 从 Python 调用** —— 会静默返回空, 让你得出"本地 0 个文件"这类错误结论;
`os.scandir` 稳定。

判读三类差集:
- 只在本地: 容器 churn 留下的陈旧文件, **正常累积, 不是错误, 别顺手批量删**
- 只在远端: 漏备(真问题)
- 同名但大小不同: 该文件被中断过(重点核对)

三者皆空 = 真正同步。

## 三、残留 `.partial` / `.tmp-dl` 清理(删除前置校验 + 清单留证)

`.partial`(中断的 rclone 目标文件)与 `.tmp-dl` 不会被自动清理, 长期累积可达几十 G。

**能不能删的判定**: 去掉后缀得到基名, **基名对应的完整文件必须同时存在于本机与源端、且两端尺寸一致**;
缺任一条件就不要删(可能是唯一一份数据)。

```python
base = re.sub(r"\.(tmp-dl|[0-9a-f]{8}\.partial)$", "", name)   # 中间产物后缀形如 .<hex8>.partial
ok = os.path.isfile(local_base) and remote.get(base) == os.path.getsize(local_base)
```

删除流程(红线合规):
1. 先出校验表(逐项 ✓ 冗余 / ⚠ 勿删), **全过才动手**;出现任何 ⚠ 就停手报告, 不要"先删能删的"。
2. 写清单: 每个被删文件的大小 + 对应完整件来源 + 时间戳 → `F:/unraid-backup/.deleted-manifest-<ts>.txt`。
3. 删除后对比 `shutil.disk_usage("F:/").free` 前后值 —— 释放量与预期不符 = 算错或删错, 立即报告。
4. 删完重跑第二节的逐文件比对, 确认"本地 == 远端"且残留为 0。

与源端无对应关系的测试残留(如 `scp-test.running`)用 `md5sum` 与同名正式备份比哈希, 一致即冗余副本。

## 四、不要做的事

- 不要在 rclone 仍在写该目录时删残留。
- 不要凭"本地比远端多"就批量删 —— 先按第二节分类, churn 陈旧文件正常存在。
- 不要把"HTTP/传输 100%"当成任务完成的证据 —— 挂起时它也显示 100%。
