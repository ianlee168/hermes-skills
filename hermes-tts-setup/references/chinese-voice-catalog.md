# Microsoft Edge TTS — Chinese voice catalog

All voices below are **free**, require no API key, and work via the `edge-tts` Python package (must be installed in `~/.hermes/hermes-agent/.venv` — see SKILL.md pitfall).

Voice list is from the public Microsoft Edge "Read Aloud" catalog. The exact set can change when Microsoft adds/removes voices; treat this as a snapshot, not a contract.

## Mandarin — zh-CN

| Voice | Personality | Best for |
|---|---|---|
| `zh-CN-XiaoxiaoNeural` | 甜美温柔少女 (most Lin Chi-ling-like) | Default Chinese female; gentle narration, weather, assistant |
| `zh-CN-XiaoyiNeural` | 活泼年轻女声 | Energetic content, kids' content, friendly chatter |
| `zh-CN-YunxiNeural` | 阳光少年男声 | Male narrator, sports, energetic |
| `zh-CN-YunyangNeural` | 专业新闻男声 | News, formal announcements |
| `zh-CN-liaoning-XiaobeiNeural` | 东北口音女声 | Comedic, dialect content |
| `zh-CN-shaanxi-XiaoniNeural` | 陕西口音女声 | Regional content |
| `zh-CN-henan-YundengNeural` | 河南口音男声 | Regional content |

## Cantonese — zh-HK

| Voice | Personality |
|---|---|
| `zh-HK-HiuMaanNeural` | 温柔粤语女声 (Hong Kong style) |
| `zh-HK-WanLungNeural` | 成熟粤语男声 |
| `zh-HK-HiuGaaiNeural` | 温柔粤语女声 (alternative) |

## Taiwanese Mandarin — zh-TW

| Voice | Personality |
|---|---|
| `zh-TW-HsiaoChenNeural` | 温柔台语女声 |
| `zh-TW-YunJheNeural` | 阳光台语男声 |
| `zh-TW-HsiaoYuNeural` | 活泼台语女声 |

## How to test a voice quickly

```bash
~/.hermes/hermes-agent/.venv/Scripts/python.exe -c "
import asyncio, edge_tts
async def go():
    c = edge_tts.Communicate('这是一段测试音频', voice='zh-CN-XiaoxiaoNeural')
    await c.save('C:/Users/<user>/AppData/Local/hermes/audio_cache/zh-test.mp3')
asyncio.run(go())"
```

Or run `scripts/verify_tts.py` from this skill.

## How to set as default

```bash
hermes config set tts.edge.voice zh-CN-XiaoxiaoNeural
```

(See SKILL.md for the config-edit guardrail — direct file edit is blocked.)

## SSML controls (advanced)

`edge-tts` accepts style/role/pitch/rate/volume via the SSML path. The Python `Communicate` class supports `rate`, `volume`, and `pitch` kwargs directly:

```python
c = edge_tts.Communicate(
    text,
    voice="zh-CN-XiaoxiaoNeural",
    rate="+10%",   # -50%..+100%
    pitch="+5Hz",  # -50Hz..+50Hz typical
    volume="+0%",
)
```

For style/role (e.g. "cheerful", "sad", "newscast"), you must build SSML manually — the `edge-tts` library does not expose those through the high-level `Communicate` API.
