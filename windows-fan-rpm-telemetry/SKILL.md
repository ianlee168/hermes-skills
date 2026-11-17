---
name: windows-fan-rpm-telemetry
description: Use when asked which fan is noisy or to read fan RPM.
category: devops
---

# Windows Fan RPM / Temperature Telemetry (LibreHardwareMonitor + data.json)

Goal: read real fan RPM, PWM and temps without HWiNFO's 12-hour Shared Memory limit
and without a Stream Deck plugin. The whole chain is an HTTP JSON endpoint.

## Why not the alternatives

- **HWiNFO64 free**: Shared Memory Support stops after 12 h and must be re-enabled
  (Settings → **Main Settings** → `Shared Memory Support`; or `SensorsSM=1` in
  `HWiNFO64.INI [Settings]`). Pro removes the limit.
- **OpenHardwareMonitor**: unmaintained (last push 2024-07, no GitHub releases).
  New platforms (Zen5) are unsupported.
- **streamdeck-ohs**: a Stream Deck *display* plugin only — it reads
  `http://localhost:8085/data.json` (`propertyinspector/js/openhardware.js`) and paints
  keys. No API, no shared memory. Its value is proving the HTTP link works.
- **LibreHardwareMonitor (LHM)**: maintained (v0.9.6, repo active), MPL-2.0, serves the
  same `data.json` from its `HttpServer` (`LibreHardwareMonitor.Windows.Forms/Utilities/HttpServer.cs`),
  plus a Prometheus endpoint. Gigabyte boards: `Lpc/IT87XX.cs` covers IT8689E/IT8696E and
  there are Gigabyte-specific controllers (`EcioPortGigabyteController`, `IsaBridgeGigabyteController`).

## Setup (portable, no install)

```bash
mkdir -p /d/hermes-test/lhm && cd /d/hermes-test/lhm
curl -sL -o LHM.zip "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip"
unzip -o -q LHM.zip -d .
```

**Pitfall that costs the most time:** LHM persists its own settings via
`Path.ChangeExtension(Application.ExecutablePath, ".config")` — for
`LibreHardwareMonitor.exe` that is **`LibreHardwareMonitor.config`**, NOT
`LibreHardwareMonitor.exe.config` (the latter is the .NET runtime config and is ignored).
Pre-seed the web server there so no GUI clicking or HKCU spelunking is needed:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <appSettings>
    <add key="runWebServerMenuItem" value="true" />
    <add key="listenerPort" value="8085" />
  </appSettings>
</configuration>
```

Keys come from `UI/MainForm.cs` (`runWebServerMenuItem`, `listenerPort`, default 8085).
Start it elevated — sensors need the kernel driver, so a non-elevated start reads almost
nothing:

```bash
powershell -NoProfile -Command "Start-Process -FilePath 'D:/hermes-test/lhm/LibreHardwareMonitor.exe' -Verb RunAs"
```

Fetch (native Windows curl cannot write to an MSYS `/d/...` path — use `D:/...`):

```bash
curl -s -m 15 -o D:/hermes-test/lhm_data.json -w "http=%{http_code} bytes=%{size_download}\n" http://localhost:8085/data.json
```
`bytes=0` + `http=200` = write path problem, not a server problem. LHM uses `HttpListener`,
so `netstat -ano | grep 8085` legitimately shows **PID 4 (System)** — that is http.sys, not a
foreign process.

## Reading it

`data.json` is a tree: each node has `Text`, `Value`, `Type`, `Children`. Walk recursively and
filter on `Type` ∈ `Fan` / `Temperature` / `Control` (`Control` values are `-` when the chip
has no write support, e.g. IT8696E — you cannot PWM fans through LHM on that board).

Fan channels are generic (`Fan #1..6`); unused headers read `0 RPM`. To map a channel to a
real header without opening the case, run a short CPU burn and watch which channels follow:

```python
BURN = "import time\nt=time.time()\nwhile time.time()-t<15:\n    x=0\n    for i in range(100000): x+=i*i%7"
# spawn 8x subprocess.Popen([sys.executable,"-c",BURN]) and sample data.json every 2 s
```
Sample from **subprocesses**, not `multiprocessing.Process` — the Hermes execute_code kernel
cannot pickle a `__main__` function (`PicklingError: Can't find __main__.burn`).

Interpretation:
- big, fast RPM swing tracking CPU temp → CPU cooler fan;
- smaller swing tracking CPU temp → case fan on a CPU-based curve;
- flat RPM that ignores both CPU and board temp → fixed curve / pump / case fan on a
  system-temp curve.
- GPU fans at `0 RPM` with the GPU at ~30 W and `P3` = zero-fan idle; a noisy machine with
  0 % GPU fan is never the graphics card.

## Gigabyte GCC's Fan module is NOT a reliable control path (measured 2026-11-17)

On a B850M AORUS ELITE WIFI7 ICE-P (ITE IT8696E) GCC's Fan page **loads and displays**
`<Control Center>\Fan\Profile-0.xml` correctly (SmartFanMode / StairStepMode / RpmFixedMode
per header, X = degC, Y = duty*255/100) but its **套用 (Apply) button did nothing twice**,
in two different ways:

- first apply: EC duties dropped to the 27% floor while the CPU was at 67 degC and climbed to
  69 degC (the curve should have asked for ~72%) - i.e. it applied with a wrong temperature source;
- second apply: EC duties did not change at all for 20 s and `Profile-0.xml` mtime never moved
  (GCC never persists an apply, so a reboot reverts to the BIOS curve).

Consequence: never present GCC as the durable answer. Editing `Profile-0.xml` directly is safe
and does get picked up by the UI, but it is not a control path on its own. The durable options are
the **BIOS Smart Fan 6** curve (survives reboots, authoritative at POST; Gigabyte AMI path:
Del -> Easy Mode "Smart Fan 6", or F2 -> Tweaker -> Smart Fan 6; per header set Fan Control =
Manual, Fan Stop = Disabled, then the temp/duty points) or a startup daemon that writes PWM
itself. Also note GCC is a High-integrity process: computer_use input to it returns
`background_uipi_blocked`, so its GUI cannot be automated from the agent at all.

### Verified end state worth recognising

With the BIOS curve set to 33% at 40 degC / 39% at 50 / 49% at 60 / 100% at 70 (CPU header) and
35/49/100% at 40/50/60 degC (case headers): idle duty self-adjusts ~42-44% (1100 RPM / CPU 52 degC),
an 8-thread burn ramps to 100% (2368 / 1776 / 2015 RPM) with the CPU plateauing at 83-84 degC, and
it drops back to 42% within 15 s after the load ends. Duty that *changes with temperature* while
no daemon is running is the proof that the firmware - not software - owns the fans.

## Reporting to the user

State GPU fan % and temp first (settles "is it the graphics card?" in one line), then the
per-channel RPM table, then which channels follow load. Tuning advice belongs in the BIOS fan
curve (Gigabyte Smart Fan 6) or GCC — never suggest a driver-level PWM tool for a chip LHM
reports `-` for.

Stop/cleanup: `Stop-Process -Id <pid> -Force` needs elevation (the process is elevated);
run it from an elevated shell or leave it and tell the user. It is portable — deleting
`D:\hermes-test\lhm` removes it completely.
