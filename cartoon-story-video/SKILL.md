---
name: cartoon-story-video
description: Use when turning a joke/story into a narrated cartoon video.
version: 1.0.0
author: Hermes Agent (50.110)
license: MIT
platforms: [windows, linux, macos]
prerequisites:
  commands: [ffmpeg, ffprobe]
  python: [PIL, numpy, edge_tts]
metadata:
  hermes:
    tags: [video, cartoon, animation, tts, ffmpeg]
---

# 故事/段子 → 卡通小视频(全程本地生成)

纯代码流水线,不依赖任何生图 API:edge-tts 出旁白 → Python+PIL 逐帧画扁平矢量卡通 → ffmpeg 编码 + 轻音乐 + 音效 + 响度归一。
实测产出一支 77 秒、1280x720、25fps、3.7MB 的九场景故事片,端到端约 4 分钟。

## When to use

- 用户给一段文字/笑话/童话,想要"小视频"
- 需要字幕、旁白、分镜节奏可控(而不是靠生图模型碰运气)
- 机器上没有可用的图像生成 API,或不想为每帧付费

## 目录结构(工作区放 D:\hermes-test 这类非系统盘)

```
<proj>/
  audio/    s01.mp3… narration.wav music.wav ding.wav
  cartoon.py  画布封装 Cv + 角色(男人/女人/猴子) + 背景/渐晕
  scenes.py   每个场景一个 paint(cv, t, D)：t=场景内秒数, D=场景时长
  render.py   时间轴 + 音频拼接 + 逐帧管道给 ffmpeg + 混音
  stills.py   只出静帧,先审画面再整片渲染
```

## 流程

1. **先写分镜台词**(每场景 1–3 句,带"女人/老板"这类指代),再逐条 TTS:
   ```python
   c = edge_tts.Communicate(text, "zh-CN-XiaoxuanNeural", rate="+6%")
   await c.save(f"audio/s{i:02d}.mp3")
   ```
2. **用 ffprobe 量每条时长**,时间轴 = `PRE(0.45) + 语音 + POST(0.75)`;场景时长由此确定,画面与旁白天然对齐。
3. **画布封装**:所有坐标用 1280x720 逻辑空间书写,`Cv` 内部乘 `S=2` 超采样,最后 `resize((1280,720), LANCZOS)` + 渐晕(central vignette)。
4. **每个场景一个纯函数** `paint(c, t, D)`:只依赖 t 做动画(走路摆腿 sin、呼吸、眨眼、气泡淡入用 `ease(t,a,b)` smoothstep),无状态 → 任意帧可单独渲染,方便出静帧审图。
5. **先出静帧审图**(stills.py 每场景取 60%/98% 两帧),用视觉检查"有没有浮空怪块/文字溢出/角色被气泡挡住",改完再整片跑。
6. **逐帧写进 ffmpeg 的 stdin**(rawvideo rgb24),不要落盘 PNG 序列:
   ```python
   p = subprocess.Popen(["ffmpeg","-y","-f","rawvideo","-pix_fmt","rgb24","-s","1280x720",
       "-r","25","-i","-","-c:v","libx264","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart", out],
       stdin=subprocess.PIPE)
   for i in range(n): p.stdin.write(img.tobytes())
   ```
   1940 帧约 3 分钟(单帧 0.1s 量级)。
7. **配乐用 numpy 合成**,不要找素材:八分音符琶音 + 每小节根音拨弦(指数衰减+谐波),`volume=0.16` 垫底;音效(门铃)用双音正弦叠指数衰减,`adelay` 精确放到场景时刻。
8. **响度归一**:`-af loudnorm=I=-16:TP=-1.5:LRA=9`(纯 `amix` 后常见 mean −26dB,手机外放太小)。
9. **验收**:`ffprobe` 看时长/分辨率/流,`volumedetect` 看 mean/max,再从成片按时间点抽帧做视觉复核。

## 画面配方(这套配色/比例已验证好看)

- 底色:奶油 `(255,249,236)` → 桃 `(255,226,200)` 竖向渐变;描边统一 `INK=(62,48,45)`;纸底 `PAPER`。
- 角色高约 226px(女人)/120px(猴子),`woman(c,x,y,s)` 的 `y` 是两脚之间:hip=−95, shoulder=−168, head=−202, r=27。
- 台标/章节小标签 `bubble_title()` 放左上角,给成片"分镜感"。
- 场景切换用**过白淡入淡出**(前/后各 0.18s 与纸色 blend),比黑场温和,也不会打乱配音时间轴。

## 坑(踩过)

- **绝对不要混用 `c.d.ellipse(...)`(像素空间)和 `c.ell(...)`(逻辑空间)**:一旦漏写 `*S`,元素会跑到**屏幕左上角的一半位置**,表现为"莫名其妙浮着的棕色椭圆"。表现就是画面里多一个鬼影斑块 → 直接搜 `c.d.` 全改成封装方法。
- **PIL `rounded_rectangle` 要求 x1>=x0、y1>=y0**:动画中盒子会随参数收缩到反转,必须 `if x_r > x0:` 守卫,否则整帧崩 `ValueError`。
- **字体缺字 → 豆腐块**:`✦ ✓ →` 这类符号在微软雅黑里可能没有,渲染成方块。用 vector 画星形/勾/箭头(`star()`, `check()`, `arrow_right()`)。
- **文字溢出高亮框**:多行文案的高亮框高度要按行数算(`50 + 40*行数`),否则第二行掉到框外。
- **气泡别盖住脸**:punchline 气泡底边要留出角色头部空间;先按比例缩小角色(s 1.75→1.42)再定气泡位置。
- **角色在台面后方**:先画角色,再画桌面/柜台覆盖下半身,否则看起来"站在柜台上"。
- **MSYS/git-bash 调用原生程序**:`ffprobe D:/...` 可以,`ffprobe /d/...` 报 "No such file" —— 路径要写成 `D:/x/y.mp3`。
- **write_file 覆盖已存在文件会被拒**(本会话没读过全文/读的是分页视图):改版直接写新文件名(`scenes2.py`)并改 import,别和工具较劲。
- **成人向段子**:画面只演到"关门"就够,不用真的画出来;旁白可以点题,视觉保持 PG。

## 复用

换故事只改两处:台词列表(render.py/`ORDER` 之前的 TTS 脚本)与 `scenes.py` 的 painter。渲染/混音/编码那层几乎不用动。
