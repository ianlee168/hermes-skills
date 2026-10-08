# HA /config 文件层直改 + 仪表盘布局工具(实测可用)

适用：要改 Home Assistant 的 YAML 仪表盘 / 模板 / 场景 / 静态资源，但**没有 HA 登录态**、只有本机 shell。

## 入口：匿名 SMB 直通(先探，别先猜)

```bash
ls //<HA_IP>/config                 # 能列 = Samba 插件开着且未设密码(实测 guest 可写)
cp file //<HA_IP>/config/www/       # 直接写
```

- **端口 445 开着就是入口**;先探 22222(SSH 插件)/1337(Code Server)/8099(File Editor)，通常都关着。
- `net view \\<HA_IP>` 报 **1702** 是假警报(RPC)，直接访问 UNC 路径就行。
- ⚠️ **改任何文件前先建时间戳备份目录** `/config/.hermes-backup-YYYYMMDD/` 再 cp 原件——这是唯一的回头路。

## YAML 模式仪表盘的三个坑

1. **`!include` 的路径基准是仪表盘文件所在目录**,不是 /config:`dashboards/x.yaml` 里写
   `!include button_card_templates.yaml` → `Unable to read file /config/dashboards/...`；写 `../button_card_templates.yaml` 才对。
2. **button-card 模板只从仪表盘配置里读**:`button_card_templates:` 写在 configuration.yaml 顶层前端永远看不到，
   必须在仪表盘 yaml 顶层 include 一份。
3. **YAML 仪表盘每次请求重新读盘**——改完文件立刻生效，**不用重启 HA**。

验证(WS，不需要登录 UI)：

```python
{"id":1,"type":"lovelace/config","url_path":"<dashboard-path>"}
# success=false 时 error.message 自带行号与原因(如 Unable to read file …)
```

## 改完布局怎么验证(验收清单)

1. WS 拉 `lovelace/config`:`success=true` + 模板数/元素数对得上 = HA 真的解析了新文件。
   ⚠️ **改了 `!include` 的模板文件后必须再动一下仪表盘文件本身**(哪怕改一行注释)——HA 会缓存
   include 的内容，只改模板文件时 WS 返回的**仍是旧内容且不报错**。判据是把返回的模板内容
   打出来跟盘上文件对比，别凭"文件写了"宣布修好。
2. **抽配置里所有实体与 `/api/states` 对集合**——半成品仪表盘最常见的病是占位实体；
   过滤掉 `[[[ return variables.x ]]]` 这类 JS 串再比。
3. 静态资源用 `curl -o 落盘` 再 `cmp` 字节对比(**`-o /dev/null` 会报 size=0，误导**)。
4. 落点预览不要指望 HA 界面:PIL 把图钉画在底图 PNG 上给用户看，中文字体
   `ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 40)`。

## 相关 yaml 细节

- **scenes.yaml / scripts.yaml 热加载**:写完 `POST /api/services/scene/reload` 立即生效。
- **中文名会被转成拼音式 entity_id**:`name: 离家` → `scene.chi_jia`(不是 li_jia)。用 `id:` 显式指定最稳，
  **写完一定回读真实 entity_id** 再引用。
- **button-card 的 `triggers_update` 不接受 JS 模板**(只吃实体 id / `all`)；
  `custom_fields` 必须配 `styles.grid` 区域，否则多个自定义字段叠在同一格。
- **坐标从底图真实几何算**:svg `viewBox="0 0 W H"` → `left% = x/W*100`、`top% = y/H*100`；
  房间矩形直接从 `<rect>` 读，别凭感觉摆。
- **svg→png**(手机端常要 png):
  `chrome --headless=new --force-device-scale-factor=2 --window-size=W,H --screenshot=out.png file:///…/x.svg`。

## storage 模式仪表盘(概览那种):走 API,不走文件

| 模式 | 怎么改 | UI 可视化编辑器 | 自带备份 |
|---|---|---|---|
| **storage** | WS `lovelace/config/save`(可带 `url_path`) | ✅ 有(⋯→原始配置编辑器) | ❌ 没有 → **先把拉到的 config 原样存成 JSON 文件**,再动手 |
| **yaml** | 改 `/config/dashboards/*.yaml`(匿名 SMB) | ❌ 没有(整个仪表盘只读) | 自己 cp |

```python
ws: {"id":1,"type":"lovelace/config"}                        # 读:默认仪表盘(概览)
ws: {"id":2,"type":"lovelace/config","url_path":"caiping-ui"}  # 读:指定仪表盘
ws: {"id":3,"type":"lovelace/config/save","config":{...}}   # 写:整份替换(先备份!)
```

改完回读一次确认字段真的变了——**先查证再答**。两种模式的 picture-elements 官方都没有拖拽，
所以"用户想自己拖"只能自建工具(见下节)。

## 破损卡片诊断顺序(picture-elements 三查)

1. **底图**:把卡里每个 `/local/...` 都 `curl -o 落盘` 看 HTTP 码与字节数。
   ⚠️ **`/local/` 映射 `/config/www/`,不是 `/config/` 根**:图放在根目录时 URL **404 而文件确实
   存在**(`ls` 看得见)—— 别据此断定"图没丢"。修法:把文件复制进 `www/`(配置侧零改动)。
   找不到的图用 **md5 在 `/config` 树里反查同内容副本**(常见于同一张图有中英文两个文件名并存)。
2. **实体**:元素引用的每个 entity 去 `/api/states` 对集合;不存在 → 卡片报错/占位。
3. **落点**:把元素坐标叠到底图上渲染出来看(见上节 PIL 预览)，三种典型病一眼可见——
   图标**挤在一小块**、**落在墙外空白**、**某些房间一个都没有**；都是"坐标从没对着这张图量过"。

结论别停在"图补上了":底图恢复后坐标仍可能整套不对(原作者照别的图摆的)，
要一并提出"重新落位"的方案让用户定。

## 让用户自己拖位置:本机拖拽编辑器

**HA 界面里拖不了**:YAML 模式仪表盘没有 UI 可视化编辑器；就算换 storage 模式，官方 picture-elements
编辑器也只有数字框，不支持拖拽。要满足"我自己拖"只能给本机工具。

现成件在 `~/ha-caiping-editor/`:`server.py`(仅监听 127.0.0.1:8765)、`index.html`(户型图+图钉+数字微调)、
`启动拖拽编辑器.bat`、`plan.png`(从 HA `/local/floorplan.png` 缓存)。接口:
`GET /state` `GET /plan.png` `POST /save` body `{"changes":{"<视图>|<idx>":[left,top]}}`。

重建时的硬性要求:

- **只替换 left/top 两行的数值，绝不整份重写 YAML**(注释/模板引用/顺序都是用户的资产)。
- 保存流程固定 **备份 → 写 → 回读校验 → 报告**；校验不一致必须回传 `verify_failed`，不能只报"成功"。
- 图钉标签取 HA friendly_name:优先级 `name:` 字段 > 上一行注释 > friendly_name；超 16 字截断。
- 解析坑:**注释要当元素边界**(遇注释就结束当前元素收集，否则字段串到下一个)；
  同文件里 entities 卡片内嵌的 button-card 也匹配 `- type: custom:button-card`，
  **必须有 left/top 才算可拖元素**，过滤后按视图重新编号，否则序号与界面错位。
- 它是会话内后台进程，Hermes 重启即消失 → 告知用户双击 bat。
