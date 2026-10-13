# 抡锤者（lcz.me）设计参考 — BBS UI 改进目标

## 页面结构

### 分类列表页 (lcz.me/categories)
- 网格卡片布局（col-md-3 响应式）
- 每张卡片包含：emoji图标、分类名称、topics数量、posts数量、最后回复用户头像+摘要预览
- 导航栏有：Categories、Recent、Tags、Popular、Users、Groups
- 右上角有 Skins 按钮（切换主题）

### 分类详情页
- 置顶帖（PIN）带黄色背景标签
- 每帖显示：用户头像、标题、投票数、回复数、阅读数、最后回复人头像+摘要
- 右侧有 All tags 和 Topic sort 下拉菜单

## 设计要素

### 配色
- 深色主题为主
- 分类图标彩色（每类不同 bgColor）
- 卡片 hover 有轻微阴影提升

### 图标
- FontAwesome emoji 形式（、、、、、、、）
- 对应 NodeBB 的 `icon` 字段（FontAwesome class）

### 布局
- 网格 vs 列表 切换
- 卡片高度一致
- 用户头像圆形

## TechTreeHole 当前 vs 目标

| 要素 | 当前 | 目标 |
|------|------|------|
| 主题 | 默认 NodeBB 皮肤 | 深色主题 |
| 分类图标 | fa-xxx 纯色 | emoji 或彩色图标 |
| 用户头像 | 无 | 圆形头像 |
| 布局 | 简单列表 | 卡片网格 |
| 最后回复 | 仅时间 | 头像+摘要预览 |
| 置顶 | 无特殊样式 | 黄色 PIN 标签 |

## 操作建议

1. Admin → Appearance → Themes → 安装深色主题
2. Admin → Categories → 编辑每个分类：加 emoji 前缀、改 icon、改 bgColor
3. Admin → Appearance → Custom Content → 添加 CSS 改善卡片样式
4. 或考虑安装 nodebb-plugin-db-search 或 nodebb-theme-persona 等现成主题
