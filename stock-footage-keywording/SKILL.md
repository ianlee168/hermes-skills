---
name: stock-footage-keywording
description: "素材要卖(Pond5/Shutterstock)时生成上架 SEO 关键词元数据(标题+描述+40-50词)。"
version: 0.2.0
author: Hermes Agent (ianlee168)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [stock footage, keywording, microstock, SEO, metadata, 素材, 关键词]
    related_skills: []
---

# Stock Footage Keywording(卖家侧素材上架元数据)

## When to Use / 何时用

用户要给自己拍摄/制作的素材(视频或照片)生成**上架卖钱的元数据**时用:
- 目标平台:Pond5 / Shutterstock / Getty Images(iStock)的**创作者上传**
- 输入:素材的画面文字描述(初版);未来接入视觉分析自动读画面(v0.2 TODO)
- 输出:Title + Description + 40–50 条四类关键词 + 合规提醒,可直接粘贴上架

不是搜 B-roll 做视频(那是买家侧,见 remotion-superpowers 的 stock-footage-workflow)。

## 铁律(决定过审与出单,不许破)

1. **准确性闸门**:每个技术词/场景词必须画面里真有。静态镜头禁写 `tracking shot`、`slow motion`;非 4K 素材禁写 `4k`、`8k`。误导性关键词 = 拒审/账号健康分受损。
2. **概念词要画面支撑**:Category 4 抽象/商业词(freedom、digital nomad、relaxation)只放画面真能支撑的。拍曼谷路边摊吃面就别写 freedom/digital nomad。
3. **真实地名是资产,不禁**:Bangkok、Thailand、street food market、tuk tuk 这类准确地名/文化词是亚洲素材卖欧美买家的核心搜索词,大胆用(前提:画面确实在那拍的)。
4. **硬排除项**:品牌名、商标、产品名、真人姓名/地址/任何 PII、logo、可辨识店面招牌——一律不进关键词、标题、描述。
5. **买家视角**:每条词过一遍——"买家会在搜索框输入这个词找我的素材吗?" 凑不够就宁缺毋滥,不同义堆砌凑数。
6. **主词前置**:输出按买家搜索权重排序——主体/动作/地点等核心词放最前,概念/氛围词殿后。

## 输出结构

### 1. Title(一句话,陈述事实,不要营销腔)
公式:**Main Subject + Action + Location + Atmosphere**
- ✅ "Woman eating street food at night market in Bangkok, Thailand"
- ❌ "Amazing Incredible Street Food Experience in Beautiful Bangkok!!!"(堆形容词 + 标题党,Shutterstock 判为劣质元数据)

### 2. Description(1–2 句事实语境)
客观描述画面内容:谁、做什么、在哪、什么光线/氛围。不要关键词堆叠,不要营销话术。

### 3. Keywords(40–50 条,逗号分隔,去重,全英文)
按四类产出,每类再展开买家搜索同义词(英/美拼写:holiday/vacation, colour/color;单复数)和用途场景词(commercial, documentary, travel vlog, background)。
**排序规则**:最终列表按权重从高到低(主体→动作→地点→氛围→镜头→概念),前 5 词必须是核心主词。

| 类别 | 内容 | 示例(曼谷夜市吃面) |
|---|---|---|
| 1 主体与动作 | 主/次主体、身体动作、服饰、食物物件 | woman, asian woman, eating, street food, noodles, bowl, chopsticks, tourist |
| 2 环境氛围 | 地点、时段、光线、色调、季节、天气 | night market, street vendor, Bangkok, Thailand, night, neon lights, steam, vibrant, crowded |
| 3 镜头技术 | **只写真有的** | handheld shot(真的手持才写), close-up, shallow depth of field(真的浅景深才写), 4k(文件真是 4K 才写) |
| 4 概念商业 | 画面支撑的抽象/商用场景词 | asian food culture(画面能支撑才写), travel destination, eating out, local life |

### 4. 合规提醒(输出末尾附,不是关键词)
- 画面有**可辨认人脸** → `⚠️ 需 model release 才能当商业素材卖`
- 出现**品牌/logo/店面招牌/标志性建筑** → `⚠️ 需 property release 或剪掉`
- 素材来源:**AI 生成内容 Shutterstock 不收**,别标错

## 工作流(初版:文字输入)

1. 用户给素材描述(或逐镜头描述一段视频)
2. 按铁律 1–4 先过一遍画面事实
3. 产出四段式输出(Title/Description/Keywords/合规提醒),关键词按权重排序
4. 关键词清点:40–50 条;不足 40 说明理由,不硬凑
5. **(可选校准)**:拿核心词到 Xpiks / IMS Keyworder 反查同类热卖素材对照补漏。外部工具建议只作校验,不直接照抄(可能带垃圾词)

## 平台上限(已核实 2026-09)

| 平台 | 关键词上限 | 官方建议 |
|---|---|---|
| Shutterstock | 硬上限 50(所有内容类型) | 精准优先,垃圾词触发拒审/spam flag |
| Pond5 | 上限 50(下限 5) | 「Master Your Metadata」建议 40–50 条 |
| Getty/iStock | 未逐条核实,以上传后台提示为准 | 同卖家侧原则 |

## 待优化清单(慢慢迭代)

- [x] 词库积累 → 改用 Xpiks / IMS Keyworder 反查校准(2026-09-03),不再手攒词表
- [ ] 视频多镜头 → 逐场景多组元数据的拆分规则
- [ ] 拒审原因 → 规则回写(用户反馈迭代)
- [x] CSV/上传导出 → 直接用 Xpiks / Microstock+ 自带导出,skill 不自造格式
- [ ] v0.3:ffmpeg 抽关键帧 → 多模态模型(Gemini Flash / GPT-4o 类)直读画面 → 自动出四段式(先定跑哪台机器、走哪个 API)
- [ ] 各平台 Title/Description 长度限制核实(Getty 分平台规则差异)

## 配套外部工具(已核实 2026-09)

AI 初稿 → 工具校准是行业通行闭环;生成后可用下列工具反查验证:

| 工具 | 类型 | 干什么 | 备注 |
|---|---|---|---|
| Microstock+(ex-StockSubmitter) | 云平台 | 一次上传分发 33+ 平台;Quickmeta 按缩略图找"元数据 donor"模式 | 免费层 33 次/平台/月;stocksubmitter.com 是它的旧版同源,不是两家 |
| Xpiks | 开源桌面 | 关键词建议(Shutterstock/Adobe/本地库反向检索)、AI keywording、拼写/去重、CSV 导出、FTP/SFTP | 免费核心;Pro 约 $7/月;免费层 60 查询/日/源(全用户共享限额) |
| IMS Keyworder(ImStocker) | 网页 | 输入核心词 → 选相似图 → 挑高权重词 | 免费在线 |
| MicrostockGroup Keyword Tool | 网页 | 老牌免费反查 | 只支持 photo/illustration/vector 类型 |

⚠️ CyberStock 等"AI 关键词工具"多为订阅引流产品,"50M+ 真实买家搜索"类数据无独立来源,慎作依据。

## 版本记录

- **0.2.0(2026-09-03)**:新增铁律 6 主词前置排序;新增"配套外部工具"章节(Microstock+=StockSubmitter 换代、Xpiks 开源、TagsFinder 实为 IMS Keyworder 类,均查证);工作流加"反查校准"可选步。
- **0.1.0(2026-09-03)**:初版。四类关键词结构 + 准确性/概念词/地名/排除项铁律 + 平台上限核实(Pond5 官方 40–50 建议、Shutterstock 50 硬顶)。输入限文字描述。
