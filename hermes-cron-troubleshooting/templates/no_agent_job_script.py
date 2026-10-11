#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skeleton for a Hermes cron `no_agent` job script.

Copy to <HERMES_HOME>/scripts/<job>.py, then edit only CONFIG and WORK below.
Register / convert with:
    hermes cron edit <job_id> --no-agent --script <job>.py
(.sh/.bash runs under Git Bash; any other suffix runs under sys.executable, so
prefer .py — it does not depend on bash being on PATH.)

Why a script instead of an agent job: a no_agent job short-circuits BEFORE the
agent/model client is constructed, so it is immune to whatever breaks the
gateway's import environment, needs no model pinning, and costs no tokens.

Enforced shape — every piece earns its place:
  1. explicit timeout on every subprocess: the job-level default is 3600s, and a
     timed-out child (rclone/du/find) can survive the kill as an orphan;
  2. overlap guard: lock records a pid, staleness = pid dead OR age ceiling, and
     the lock file is NEVER unlinked (deleting needs user consent);
  3. append-only receipt log so the next day has a trend to read;
  4. fixed exit codes: 0 ok / 1 real failure / 3 already running;
  5. stdout contract: print the report (no_agent + empty stdout = no delivery);
  6. error classification: a sync tool's "completed with errors" is not
     automatically a failure when the source is live. Classify, cap, report.

Red line for any script that touches user data/machines: COPY AND READ ONLY.
Never delete, move or rename — not even old outputs, not even its own lock.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------------- CONFIG
HERMES_HOME = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\<user>\AppData\Local")) / "hermes"
RECEIPT_LOG = HERMES_HOME / "logs" / "<job>-receipts.log"
LOCK_FILE = HERMES_HOME / "scripts" / ".<job>.lock"
LOCK_STALE_SECONDS = 90 * 60
LOCK_NO_PID_SECONDS = 20 * 60          # legacy lock without a pid: shorter grace

TOOL = shutil.which("<tool>") or r"C:\path\to\<tool>.exe"   # never assume PATH
TOOL_CONF = r"C:\Users\<user>\AppData\Roaming\<tool>\<tool>.conf"
T_STEP_A, T_STEP_B, T_QUERY = 420, 1800, 300

BENIGN = re.compile(          # "live source changed under us" = not a failure
    r"(failed to set directory modtime|chtimes|ipc-?socket"
    r"|Open failed: file does not exist|failed to open source object)",
    re.I,
)
STATS_LINE = re.compile(r"\s*(Errors|Checks|Deleted|Transferred|Elapsed time)\s*:")
BENIGN_CAP = 200              # a flood of "benign" errors is a real failure


# -------------------------------------------------------------------- helpers
def run(cmd: list[str], timeout: int) -> tuple[int, str, float]:
    """Run cmd, combine output, kill on timeout. Lossy UTF-8 decode on purpose:
    the Windows console is GBK and a strict decode raises inside the reader
    thread, which loses the output AND the run."""
    started = time.monotonic()
    env = dict(os.environ)
    env.setdefault("HOME", os.environ.get("USERPROFILE", r"C:\Users\<user>"))
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.returncode, proc.stdout or "", time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return 124, f"{partial}\n[TIMEOUT after {timeout}s] {cmd[0]}", time.monotonic() - started
    except OSError as exc:
        return 127, f"[OSError] {exc}", time.monotonic() - started


def pid_alive(pid: int) -> bool:
    """Liveness without signalling (os.kill(pid, 0) is not reliable on Windows)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def classify_errors(out: str) -> tuple[int, list[str]]:
    """(benign_count, genuinely_bad_lines). Stats counters are not error events."""
    benign, bad = 0, []
    for line in out.splitlines():
        if not re.search(r"\berror", line, re.I):
            continue
        if STATS_LINE.match(line):
            continue
        if "Failed to " in line and " with " in line and re.search(r"\d+ errors", line):
            continue                      # summary line; per-error lines decide
        if BENIGN.search(line):
            benign += 1
        else:
            bad.append(line.strip()[:220])
    if benign > BENIGN_CAP:
        bad.append(f"benign-error flood: {benign} > cap {BENIGN_CAP}")
    return benign, bad


def guards() -> int | None:
    """Overlap guard. Returns an exit code to bail with, or None to proceed."""
    if LOCK_FILE.exists():
        raw = LOCK_FILE.read_text(encoding="utf-8", errors="replace").strip()
        age = time.time() - LOCK_FILE.stat().st_mtime
        m = re.search(r"pid=(\d+)", raw)
        holder = int(m.group(1)) if m else 0
        ceiling = LOCK_STALE_SECONDS if holder else LOCK_NO_PID_SECONDS
        if age < ceiling and (holder == 0 or pid_alive(holder)):
            print(f"跳过：上一次仍在运行（pid={holder or '未知'}，锁 {int(age)}s 前更新）。")
            return 3
    LOCK_FILE.write_text(
        f"pid={os.getpid()} at={datetime.now().isoformat(timespec='seconds')}",
        encoding="utf-8")
    return None


# ----------------------------------------------------------------------- WORK
def main() -> int:
    now = datetime.now()
    started = time.monotonic()
    lines: list[str] = [f"<job> {now:%Y-%m-%d %H:%M}"]
    failures: list[str] = []

    bail = guards()
    if bail is not None:
        return bail
    if not TOOL or not Path(TOOL).exists():
        print("失败：找不到工具可执行文件。")
        return 1

    # --- step A ---------------------------------------------------------
    rc, out, secs = run([TOOL, "--config", TOOL_CONF, "<args>"], T_STEP_A)
    benign, bad = classify_errors(out)
    if rc == 0 or (not bad and benign):
        note = f"，良性 churn 错误 {benign}" if benign else ""
        lines.append(f"stepA: ✓ {secs:.0f}s{note}")
    else:
        failures.append(f"stepA rc={rc}")
        lines.append(f"stepA: ✗ rc={rc} ({secs:.0f}s) — " + (" | ".join(bad[:3]) or out.strip()[-300:]))

    # --- step B, then verification (query the target, never a slow du) ---
    rc, out, secs = run([TOOL, "--config", TOOL_CONF, "size", "--json", "<target>"], T_QUERY)
    try:
        total = json.loads([l for l in out.splitlines() if l.strip().startswith("{")][-1])
        lines.append(f"核对: {total['count']} 项 / {total['bytes']} 字节")
    except Exception:
        failures.append("verify query failed")
        lines.append(f"核对: ✗ {out.strip()[-200:]}")

    elapsed = time.monotonic() - started
    lines.append(f"结果: {'成功' if not failures else '有失败: ' + '; '.join(failures)}（总耗时 {elapsed:.0f}s）")
    report = "\n".join(lines)
    print(report)

    try:
        RECEIPT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with RECEIPT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"=== {now:%Y-%m-%d %H:%M:%S} rc={1 if failures else 0} elapsed={elapsed:.0f}s ===\n")
            fh.write(report + "\n")
    except OSError as exc:
        print(f"[warn] receipt not written: {exc}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
