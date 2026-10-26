# 从上游镜像装一个新应用到 Unraid（原生容器 + 模板）

适用:用户丢来一个 GitHub 仓库/Hub 镜像(Dockerfile、compose.yaml),要求"装到 Unraid 的 docker 里"。
目标不是"跑起来一个容器",而是:开机自启、Docker 页能管、数据进 appdata 备份范围、并且**有实测证据**说明它能读到宿主机的数据。

## 0. 摸底(动手前一次做完)

```bash
ssh root@192.168.50.1 '
  netstat -tlnp | grep -E ":<期望端口>"                 # 端口占用
  ls -la /dev/dri/; getent group video render            # 核显转码节点与组号
  docker ps -a --format "{{.Names}}\t{{.Image}}\t{{.Status}}" | head -50
  grep -hE "shareUseCache|shareExport" /boot/config/shares/*.cfg
  df -h /mnt/user /mnt/cache
  ls /mnt/user/                                          # 有哪些共享可放数据
'
```

选媒体/大数据的落点:只能选 `shareUseCache="no"`(直写阵列)的共享或新建目录。cache-backed 共享(`shareUseCache="yes"`)放几十上百 GB 的媒体会写爆 cache,进而把跑在它上面的 VM 打成 paused。

## 1. 目录与属主

```bash
mkdir -p /mnt/user/appdata/<app> /mnt/user/<media-root>
chown -R 1000:1000 /mnt/user/appdata/<app> /mnt/user/<media-root>
```

- `/data` 用 bind,**不用 named volume**(卷在 docker.img,不进 appdata 备份、盘满先炸)。
- 需要 Windows 拖文件进去的投片目录再 `chmod 777` + 见第 5 节 SMB。

## 2. 拉镜像(后台 + 轮询)

```bash
nohup docker pull <repo>:<tag> > /tmp/<app>-pull.log 2>&1 &
# 判活:日志每层完成才打一行,静默 = 大层在下载
du -sm /var/lib/docker/tmp      # 数值持续增长 = 在动
pgrep -f "docker pull"          # 还在 = 没死
docker images | grep <repo>     # 出现 = 完成
```

先算总量再决定等多久(Docker Hub v2 API):

```bash
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:<repo>:pull" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" https://registry-1.docker.io/v2/<repo>/manifests/<tag>   # 取 amd64 的 digest
curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.manifest.v1+json" https://registry-1.docker.io/v2/<repo>/manifests/sha256:<digest> -o m.json
grep -o '"size": *[0-9]*' m.json | tr -d '" ' | awk -F: '{s+=$2} END {printf "total=%.0f MB\n", s/1048576}'
```

实测这条家宽线路 Docker Hub 常见 ~0.4 MB/s(出口走代理,量的是共享节点 IP),250MB 级镜像 10 分钟上下;别在前台 ssh 里等,会超时。

## 3. 起容器

```bash
docker run -d --name <Name> --init --restart unless-stopped --stop-timeout 75 \
  -p <hostPort>:<containerPort> \
  -e <VAR>=<value> \
  -v /mnt/user/appdata/<app>:/data \
  -v /mnt/user/<media-root>:/media:rslave \
  --device /dev/dri/renderD128 --group-add <video/render GID> \
  <repo>:<tag>
```

- 有核显就带上 `--device /dev/dri/renderD128`;节点权限是 `crwxrwxrwx root:video` 时其实世界可读写,`--group-add 18` 只是保险(组号以 `getent group video` 为准)。
- 媒体挂载要写才加 `rslave`(容器跟着宿主机挂载变化走),只读场景用 `:rslave` + 应用侧只读。

## 4. 让它在 Docker 页里可管理 + 开机自启

模板 `/boot/config/plugins/dockerMan/templates-user/my-<Name>.xml`(最小骨架,`Config` 的 `Type` 取值:`Port` / `Path` / `Device` / `Variable`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Container version="2">
  <Name>App</Name>
  <Repository>repo/app:tag</Repository>
  <Registry>https://hub.docker.com/r/repo/app</Registry>
  <Network>bridge</Network>
  <Privileged>false</Privileged>
  <Support>https://github.com/owner/repo</Support>
  <Project>https://github.com/owner/repo</Project>
  <Overview>一段说明 + 首次登录方式 + 数据目录不要删</Overview>
  <Category>MediaApp:Video Tools:</Category>
  <WebUI>http://[IP]:[PORT:8900]/</WebUI>
  <Icon>https://raw.githubusercontent.com/owner/repo/master/resources/logo.png</Icon>
  <ExtraParams>--init --stop-timeout=75 --group-add 18</ExtraParams>
  <Config Name="WebUI 端口" Target="8900" Default="8900" Mode="tcp" Type="Port" Required="true">8900</Config>
  <Config Name="数据目录" Target="/data" Default="/mnt/user/appdata/app" Mode="rw" Type="Path" Required="true">/mnt/user/appdata/app</Config>
  <Config Name="媒体目录" Target="/media" Default="/mnt/user/media-root" Mode="rw" Type="Path">/mnt/user/media-root</Config>
  <Config Name="渲染设备" Target="" Default="" Mode="" Type="Device">/dev/dri/renderD128</Config>
  <Config Name="转码后端" Target="APP_BACKEND" Default="auto" Mode="" Type="Variable" Display="advanced">auto</Config>
</Container>
```

写之前用 Python 验一遍能解析(`xml.etree.ElementTree.parse`),别把坏的 XML 丢进 flash。

自启(注意是**文件**不是目录):

```bash
grep -q "^<Name>$" /var/lib/docker/unraid-autostart || echo <Name> >> /var/lib/docker/unraid-autostart
```

## 5. 给用户一个投文件的入口(SMB)

`smb-extra.conf` 追加共享 + 热重载(不打断已有连接),细节见 SKILL.md 的 "Adding an SMB share" 一节:

```bash
chmod 777 /mnt/user/<media-root>          # 容器写(UID 1000)与 SMB 写(force user=nobody)都要能进
cat >> /boot/config/smb-extra.conf << 'EOF'
[<share>]
	path = /mnt/user/<media-root>
	public = yes
	writeable = yes
	force user = nobody
EOF
smbcontrol smbd reload-config
```

从 Windows 验证一律用 `ls "//Ians/<share>/"`;**`//192.168.50.1/<share>/` 报 Permission denied 是 Win11 拒绝 guest 认证,不是共享配错**(本机连 `//192.168.50.1/NAS` 也拒)。顺手 `cp` 一个小文件进去 = 证明写权限。往目录里放一份 `使用说明.txt` 比放测试垃圾有用。

## 6. 验收阶梯(必须都跑到)

1. `docker ps --filter name=<Name>` → `Up ... (healthy)` + 端口映射对。
2. `docker logs <Name> | head -40` → 看初始化日志里的**警告**(常见的"某目录未配置")。
3. **应用自己的体检命令**:很多应用带 `doctor` / `status` / `scan`(先 `docker exec <app> <cli> --help` 看有哪些子命令)。`doctor` 全绿 + 只有"未使用的源未配挂载"这类预期 warning 才算通。
4. **端到端一条真数据**:往媒体目录写一个能解码的小样本(容器内 `ffmpeg -f lavfi -i testsrc=size=320x240:rate=10 -t 2 -pix_fmt yuv420p /media/TEST-001.mp4`),跑应用自己的扫描命令,确认索引条数 +1。只证明"容器 healthy"是假验收。
5. 网络面:`curl -s -o /dev/null -w "%{http_code}" http://<host>:<port>/`(3xx → 登录页=正常)。
6. 硬解:`docker exec <app> vainfo --display drm --device /dev/dri/renderD128` 能列出 H.264/HEVC 的 `EncSlice` 才算硬件编码可用。

## 7. 路径映射:媒体库类应用最容易静默失败的地方

以 Peach(蜜桃)为例,它**数据库永远存 Windows 格式路径**,Docker 上必须成对配置,否则"能扫到文件但打不开":

```toml
[media.locations]      # 数据库里的前缀,Linux 上不要求真实存在
local = 'R:\media'
[media.mounts]         # 容器内实际目录(local 的键名必须对得上)
local = '/media'
```

- 网页配置页里填的永远是**容器内**路径(`/media`),不是宿主机路径。
- 只写 `locations` 不写 `mounts` = 全库读不到文件。
- 验证:`docker exec <app> scan local` 输出 `✓ local: N 文件`,`status` 里能看到 video 条数。
- 已有数据库时 `locations` 不能改(它匹配库里已有路径),搬目录只能改 `mounts` 和容器挂载。

同类应用的通用判据:先看它"数据库里存的路径"和"实际读取路径"是不是两套配置,再动手;改配置前备份 `config.toml`。

## 8. 交接口径

报告里给全这四样,用户才不用回来问:网页地址 + 首次登录凭据的**获取命令**、数据目录(以及它已落在 appdata 备份范围)、媒体投片入口(`\\Ians\<share>`)、以及**没配上的能力**(如缺 CloudDrive2 → 网盘源不可用)。验证用的测试样本要明说位置,方便用户自己删。
