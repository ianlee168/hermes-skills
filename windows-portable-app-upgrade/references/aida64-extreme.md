# AIDA64 Extreme 便携版（本机实例）

先按 `windows-portable-app-upgrade` 的通用步骤走；本页只是这个软件的具体坐标与已知差异。
路径/版本会变，动手前用 `ls` + exe FileVersion 复核一遍。

## 现场

| 项 | 值 |
|---|---|
| 安装位置 | `F:\Download\Compressed\aida64extreme800\`（便携版；目录名里的 800 是当初 8.00 时代留下的，不是版本号） |
| 旧版 | exe FileVersion **8.30.8300**（2026-04-28） |
| 设置 | `aida64.ini`，**UTF-16LE**，约 2.4 MB，退出时回写（内有 `NoRegistry=0`，UI 状态另有注册表一份） |
| 授权现状 | `HKCU\Software\FinalWire\AIDA64` 只有 `LastUsedBuild` / `TrialCount`，**没有 LicenseKey** ⇒ 这台机器一直在试用跑；正版 key 只在用户自存的 `pkey.txt` 里 |
| 自定义资源 | `SensorPanel\`（36 个文件：表盘 PNG + 布局）；漏拷就得重做面板 |
| 厂商数据库 | `aida64.dat`（zlib 压缩的硬件库）。旧目录那份比新版老，**不要搬回去** |
| 用户已有习惯 | 目录里自带 `Backup_AIDA64.bat` / `Restore_AIDA64.bat`（只备 ini+dat，不含 SensorPanel，也不解决退出回写） |

## 官方下载

1. `https://www.aida64.com/downloads` 里的 `Download` 按钮指向 `/downloads/<base64>=`，**直接 curl 会拿到一张 HTML 壳页**。
2. 壳页里 grep 出真链：稳版规律是 `https://download.aida64.com/aida64extreme<版本号去点>.zip`
   （例：8.40 → `aida64extreme840.zip`，备用 `download2.aida64.com`）。
3. **页面版本串与包内 FileVersion 会不一致**（实测页面写 8.40.5000、包内是 8.40.8500）——报版本时报 FileVersion。
4. beta 与稳定版同为 zip，beta 页明确写"解压覆盖原目录即保留设置与授权"；仍按 skill 的做法走**新目录**更安全。

## 升级配方（实测）

```bash
# $OLD = 旧目录，$NEW = 同级新目录（别原地覆盖）
python -c "import zipfile,os; os.makedirs(r'$NEW',exist_ok=True); zipfile.ZipFile(r'C:/.../aida64extreme840.zip').extractall(r'$NEW')"
cp -p "$OLD/aida64.ini" "$NEW/aida64.ini"     # UTF-16 原样字节复制
cp -p "$OLD/pkey.txt"  "$NEW/pkey.txt"        # 用户的 key 文本
cp -rp "$OLD/SensorPanel" "$NEW/SensorPanel"  # 面板素材，36 个文件
# aida64.dat 不拷 —— 用新版自带的
```

然后在新目录放一个 `启动AIDA64_<ver>.bat`（模板见 SKILL.md 第 5 步）：先确认 `aida64.exe` 没在跑、
再把旧目录最新的 `aida64.ini` 覆盖过来、最后启动新 exe。

## 验收 / 授权

- 帮助 → 关于：版本 8.40 + 授权不是试用。
- 授权没带过来是**预期内的**（本来就没激活过），用 帮助 → 输入产品密钥，粘贴 `pkey.txt` 里那串。
- 合法性看维护期：新版发布日要落在 12 个月维护期内，用户可把 key 丢到 `aida64.com/license-checker` 查到期日。

## 不买也能用的替代（用户问“有没有免费方案”时按需求列）

- 传感器/温度/风扇/功耗 → HWiNFO64（个人免费）、LibreHardwareMonitor（开源，可喂 Grafana / HA）
- 型号识别 → CPU-Z、GPU-Z、CrystalDiskInfo
- 烤机/稳定性 → Prime95、y-cruncher、OCCT 免费版
