#!/usr/bin/env python3
"""DeepSeek 计费时段标签（北京时间，UTC+8）。

官方规则（api-docs.deepseek.com/quick_start/pricing）：
  峰时 = 工作日（周一至周五，不含中国法定节假日）09:00-12:00 与 14:00-18:00
  其余全部为谷时（含周末与节假日全天），谷时价 = 峰时价的一半
输出一行，直接贴在回答末尾。

措辞规则：谷时必须写清原因（周末全天 / 非峰时段），切换点带星期，
否则单个时间点会被误读成「现在就是峰时」。
"""
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))
PEAK_WINDOWS = [(9, 12), (14, 18)]  # 北京时间，左闭右开

now = datetime.now(CST)
wd = now.weekday()  # 0=Mon
in_peak = wd <= 4 and any(
    now.hour >= s and (now.hour, now.minute) < (e, 0) for s, e in PEAK_WINDOWS
)


def fmt(dt: datetime) -> str:
    today = now.date()
    if dt.date() == today:
        return dt.strftime("%H:%M")
    if (dt.date() - today).days == 1:
        return "明天 " + dt.strftime("%H:%M")
    wd_txt = "周" + "一二三四五六日"[dt.weekday()]
    return f"{dt.strftime('%m-%d')}({wd_txt}) {dt.strftime('%H:%M')}"


# 找下一个切换点（只向前扫 8 天，足够）
event = None
t = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
for _ in range(8 * 24 * 60):
    wd_t = t.weekday()
    peak_t = wd_t <= 4 and any(t.hour >= s and t.hour < e for s, e in PEAK_WINDOWS)
    if peak_t != in_peak:
        event = t
        break
    t += timedelta(minutes=1)

hhmm = now.strftime("%H:%M")
if in_peak:
    print(f"{hhmm} 波峰 ¥2/¥8 每百万 · {fmt(event) if event else '?'} 转波谷(半价)")
else:
    why = "周末全天" if wd >= 5 else "非峰时段"
    tail = fmt(event) if event else "?"
    print(f"{hhmm} 波谷 ¥1/¥4 每百万({why}·峰价半) · 下次峰时 {tail}")
