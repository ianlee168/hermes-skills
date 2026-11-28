#!/usr/bin/env python3
"""Verify (and if needed re-apply) the two local core patches on this Hermes checkout.

Why this exists: `hermes update` can lose local modifications (autostash / ZIP fallback / fresh
env). After every update run this script — it proves the patches are present with behavioural
probes, not by eyeballing `git status`.

Patches (see skill devops/hermes-local-core-patches):
  1. plugins/platforms/weixin/adapter.py   channel_prompts support + session-expiry sleep 600 -> 5
  2. cron/prompt_scan.py                   _strip_doc_code_blocks() before the strict prompt scan

Usage:
  python verify_and_reapply.py            # check only, print a report
  python verify_and_reapply.py --apply    # git apply the saved patch when a check fails
"""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

HERMES_HOME = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes"
CHECKOUT = Path(os.environ.get("HERMES_INSTALL_DIR", str(HERMES_HOME / "hermes-agent")))
PATCH_DIR = HERMES_HOME / "patches"

CHECKS = [
    ("weixin: channel_prompts wired", "plugins/platforms/weixin/adapter.py", "channel_prompt=resolve_channel_prompt("),
    ("weixin: sleep 5 after session expiry", "plugins/platforms/weixin/adapter.py", "pausing for 5 seconds"),
    ("cron: code-block stripping helper", "cron/prompt_scan.py", "def _strip_doc_code_blocks("),
    ("cron: strict scan strips code blocks", "cron/prompt_scan.py", "_strip_doc_code_blocks(prompt)"),
]

PROBE = r"""
import sys
from cron.prompt_scan import _scan_cron_prompt
danger = "rm -rf " + "/"
fence = "```"
bare = _scan_cron_prompt(danger)
fenced = _scan_cron_prompt("run\n" + fence + "\n" + danger + "\n" + fence + "\nreport")
print("PROBE_BARE=" + ("BLOCKED" if bare else "PASSED"))
print("PROBE_FENCED=" + ("BLOCKED" if fenced else "PASSED"))
import plugins.platforms.weixin.adapter as w
print("PROBE_WEIXIN=" + ("OK" if hasattr(w, "resolve_channel_prompt") else "MISSING"))
"""


def find_python() -> str:
    """The managed interpreter that owns the checkout's dependencies."""
    for pat in (
        str(HERMES_HOME / "installs" / "*" / "environments" / "*" / "venv" / "Scripts" / "python.exe"),
        str(CHECKOUT / ".venv" / "Scripts" / "python.exe"),
        str(HERMES_HOME / "tools" / "python-*" / "python.exe"),
        str(CHECKOUT / "venv" / "bin" / "python"),
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return sys.executable


def static_report() -> list[str]:
    bad = []
    for label, rel, needle in CHECKS:
        path = CHECKOUT / rel
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        ok = needle in text
        print(f"  [{'OK' if ok else 'MISSING'}] {label}")
        if not ok:
            bad.append(label)
    return bad


def behaviour_report() -> dict[str, str]:
    out = subprocess.run([find_python(), "-c", PROBE], cwd=str(CHECKOUT),
                         capture_output=True, text=True, timeout=120)
    values = {}
    for line in (out.stdout or "").splitlines():
        if line.startswith("PROBE_") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    if not values:
        print("  [ERROR] probe failed to run:")
        print((out.stdout or "") + (out.stderr or "")[-800:])
    else:
        want = {"PROBE_BARE": "BLOCKED", "PROBE_FENCED": "PASSED", "PROBE_WEIXIN": "OK"}
        for key, expected in want.items():
            got = values.get(key, "?")
            print(f"  [{'OK' if got == expected else 'FAIL'}] {key}={got} (want {expected})")
    return values


def latest_patch() -> Path | None:
    hits = sorted(glob.glob(str(PATCH_DIR / "local-core-patches-*.patch")))
    return Path(hits[-1]) if hits else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="git apply the saved patch when a check fails")
    args = ap.parse_args()

    print(f"checkout: {CHECKOUT}\npython:   {find_python()}\n")
    print("static:")
    missing = static_report()
    print("behaviour:")
    values = behaviour_report()
    healthy = not missing and values.get("PROBE_BARE") == "BLOCKED" \
        and values.get("PROBE_FENCED") == "PASSED" and values.get("PROBE_WEIXIN") == "OK"
    if healthy:
        print("\nRESULT: both local patches present and live in the source tree.")
        return 0

    patch = latest_patch()
    print(f"\nRESULT: patch missing. saved patch: {patch}")
    if not args.apply:
        print("Re-run with --apply to git apply it, or reapply by hand (skill devops/hermes-local-core-patches).")
        return 1
    if patch is None:
        print("No saved patch file — reapply by hand from the skill's checklist.")
        return 1
    applied = subprocess.run(["git", "apply", "-v", str(patch)], cwd=str(CHECKOUT), capture_output=True, text=True)
    print(applied.stdout.strip() or applied.stderr.strip())
    if applied.returncode != 0:
        print("git apply failed (upstream drift) — reapply by hand from the skill checklist.")
        return 2
    print("\napplied. Re-checking:")
    missing = static_report()
    values = behaviour_report()
    ok = not missing and values.get("PROBE_FENCED") == "PASSED" and values.get("PROBE_WEIXIN") == "OK"
    print("\nRESULT:", "patched — restart the gateway to load it." if ok else "still broken, read the report above.")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
