---
name: stock-footage-keywording
description: "素材要卖(Pond5/Shutterstock)时生成上架 SEO 关键词元数据(标题+描述+40-50词)。"
version: 0.1.0
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

## 输出结构

### 1. Title(一句话,陈述事实,不要营销腔)
公式:**Main Subject + Action + Location + Atmosphere**
- ✅ "Woman eating street food at night market in Bangkok, Thailand"
- ❌ "Amazing Incredible Street Food Experience in Beautiful Bangkok!!!"(堆形容词 + 标题党,Shutterstock 判为劣质元数据)

### 2. Description(1–2 句事实语境)
客观描述画面内容:谁、做什么、在哪、什么光线/氛围。不要关键词堆叠,不要营销话术。

### 3. Keywords(40–50 条,逗号分隔,去重,全英文)
按四类产出,每类再展开买家搜索同义词(英/美拼写:holiday/vacation, colour/color;单复数)和用途场景词(commercial, documentary, travel vlog, background)。

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
3. 产出四段式输出(Title/Description/Keywords/合规提醒)
4. 关键词清点:40–50 条;不足 40 说明理由,不硬凑

## 平台上限(已核实 2026-09)

| 平台 | 关键词上限 | 官方建议 |
|---|---|---|
| Shutterstock | 硬上限 50(所有内容类型) | 精准优先,垃圾词触发拒审/spam flag |
| Pond5 | 上限 50(下限 5) | 「Master Your Metadata」建议 40–50 条 |
| Getty/iStock | 未逐条核实,以上传后台提示为准 | 同卖家侧原则 |

## 初版已知待优化清单(慢慢迭代)

- [ ] 真实买家搜索词库/类目词表(卖得好的词 vs 冷门词)积累
- [ ] 视频多镜头 → 逐场景多组元数据的拆分规则
- [ ] 拒审原因 → 规则回写(用户反馈迭代)
- [ ] 批量 CSV/上传格式输出(Pond5/Shutterstock 的 CSV 表头未核实,先不写死)
- [ ] v0.2:接入视觉分析自动读画面(需多模态模型,当前会话未挂 vision)
- [ ] 各平台 Title/Description 长度限制核实(Getty 分平台规则差异)

## 版本记录

- **0.1.0(2026-09-03)**:初版。四类关键词结构 + 准确性/概念词/地名/排除项四条铁律 + 平台上限核实(Pond5 官方 40–50 建议、Shutterstock 50 硬顶)。输入限文字描述。
