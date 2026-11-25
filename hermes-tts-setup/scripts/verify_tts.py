#!/usr/bin/env python3
"""Verify Hermes TTS edge-tts chain end-to-end.

Use this script after any TTS-related config or install change. It bypasses the
Hermes wrapper and calls edge-tts directly, so it confirms the library is
installed and the network can reach Microsoft's TTS endpoint.

Usage:
  python verify_tts.py                          # default voice + Chinese text
  python verify_tts.py --voice zh-CN-YunxiNeural --text "测试"
  python verify_tts.py --en                     # English text (Aria)

Prereq: edge-tts must be installed in hermes-agent venv:
  ~/.hermes/hermes-agent/.venv/Scripts/python.exe -m pip install edge-tts
"""
import argparse
import asyncio
import sys
from pathlib import Path

CACHE = Path.home() / "AppData/Local/hermes/audio_cache"
CACHE.mkdir(parents=True, exist_ok=True)

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_TEXT_ZH = "用户吉祥，微臣智障爱卿谨呈一段示例语音，以证 TTS 链通。"
DEFAULT_TEXT_EN = "Your Majesty, this is a sample voice to confirm the TTS chain works."



def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--text", default=None)
    ap.add_argument("--en", action="store_true", help="Use English sample text")
    ap.add_argument("--out", default=None, help="Override output path")
    args = ap.parse_args()

    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("❌ edge-tts not importable in this Python.")
        print("   If you are running this from hermes-agent venv, install it:")
        print("     ~/.hermes/hermes-agent/.venv/Scripts/python.exe -m pip install edge-tts")
        print("   If you are running system Python, this script is the wrong venv —")
        print("   invoke it with hermes-agent's python instead.")
        return 2

    text = args.text or (DEFAULT_TEXT_EN if args.en else DEFAULT_TEXT_ZH)
    safe_voice = args.voice.replace("/", "_")
    out = Path(args.out) if args.out else CACHE / f"verify-{safe_voice}.mp3"
    print(f"Synthesizing voice={args.voice!r} ({len(text)} chars) -> {out}")

    async def go() -> None:
        import edge_tts
        c = edge_tts.Communicate(text, voice=args.voice)
        await c.save(str(out))

    try:
        asyncio.run(go())
    except Exception as exc:
        print(f"❌ synthesis failed: {exc!r}")
        return 1

    size = out.stat().st_size
    if size < 5000:
        print(f"❌ output too small ({size} bytes); expected >5KB")
        return 1
    print(f"✅ wrote {size} bytes -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
