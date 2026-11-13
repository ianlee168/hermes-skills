# HA event → a popup with a picture on the Windows desktop

Use when the user wants "when X happens at home, show me the camera view on my PC"
(doorbell, gate, motion). No HASS.Agent and no MQTT are needed: Hermes already runs on
the Windows box, so one small long-running Python process can do all of it.

## Shape

```
HA WebSocket ──subscribe_events(state_changed)──► match trigger entity/text
                                                      │
                                    fetch picture ────┘──► tkinter always-on-top window
```

Keep it one file, one process, and **log every observed candidate event (plus whether a
picture was available) to a log file** — then "did it fire?" is a file read instead of
guessing. Follow up with the user only for the physical step (press the bell).

## Trigger: subscribe over the HA WebSocket

```python
async with websockets.connect(f"{HA.replace('http','ws')}/api/websocket", max_size=None) as ws:
    await ws.recv()                                                   # auth_required
    await ws.send(json.dumps({"type":"auth","access_token":TOKEN}))
    r = json.loads(await ws.recv()); assert r["type"] == "auth_ok"    # never assumed
    await ws.send(json.dumps({"id":1,"type":"subscribe_events","event_type":"state_changed"}))
    async for raw in ws:
        d = json.loads(raw)["event"]["data"]
        if d.get("entity_id") != TRIGGER_ENTITY: continue
        state = (d.get("new_state") or {}).get("state") or ""
```

- Wrap the whole thing in a `while True` + `try/except` reconnect loop with a short sleep:
  a dropped socket must not silently end the watcher.
- Match on **text**, not only entity: Mi-Home style events arrive as a message entity whose
  *state string* changes (see `xiaomi-miot-cloud-api.md` §5). Write the trigger as a small
  regex and start it broad, then narrow.
- Getting the trigger wrong is invisible without logging — log every change of the watched
  entity first, run one real-world test, then keep only the real pattern.

## Picture: pick the source, and say which one worked

| priority | source | notes |
|---|---|---|
| 1 | image URL carried by the event/message (`entity_picture`) | cloud-hosted; try with and without the HA `Authorization` header. Not guaranteed to exist |
| 2 | `GET {HA}/api/camera_proxy/camera.<x>` with `Authorization: Bearer` | returns a **live JPEG** (verified 848×480) for HA camera entities whose alerting/看家 feature is enabled |
| 3 | text-only card | still useful (who/where/time + a beep) — but tell the user the picture half is not solved yet |

Turn a device's capture features on (via the miot property API) before declaring source 2
impossible for it; a device that only pushes text for its doorbell will still push
image-bearing alarm messages if its own motion/loitering capture is enabled.

## Popup: tkinter, and the main-thread rule

```python
win = tk.Toplevel(root)                 # root = hidden Tk()
win.overrideredirect(True)              # no chrome, looks like a toast
win.attributes("-topmost", True)
win.geometry(f"{W}x{h}+{sw-W-40}+{sh-h-80}")   # bottom-right above the taskbar
win.bind("<Escape>", lambda e: win.destroy())
for w in (win, *children): w.bind("<Button-1>", lambda e: win.destroy())
win.after(25_000, win.destroy)          # auto-close
import winsound; winsound.MessageBeep(0x00000040)   # the "ding"
```

- **tkinter must own the main thread.** When the trigger loop runs in an asyncio/background
  thread, create a hidden `Tk()` on the main thread and let the worker push
  `(title, subtitle, image_bytes)` into a list that an `root.after(400, poll)` drains.
- Scale the image with Pillow to a fixed width and size the window to
  `image_height + header/footer`: a fixed-height window leaves an ugly empty band and the
  user reads that as "broken".
- A GUI started from the agent's own `terminal(background=true)` **does appear on the
  user's desktop** — use that for the demo, and verify with `computer_use`
  `capture(app="python.exe")` / `list_windows`, not by asking what they saw.

## Running it for real

- First run: ad-hoc background process, log to a file, ask the user for one real trigger
  (`请去按一下门铃`), then read the log — do not declare success from a manual self-test of
  the popup alone.
- Production: make it start at logon (Windows scheduled task at logon) or a Hermes cron job;
  a process that dies with the agent session is not a doorbell.
- Read `HASS_URL` / `HASS_TOKEN` from `~/AppData/Local/hermes/.env` at launch rather than
  pasting the token into the script.

## Pitfalls

- ❌ Promising "doorbell rings → PC shows the camera" before checking that the event
  actually reaches HA *and* that some source can produce an image. Verify the arrival path
  first (`xiaomi-miot-cloud-api.md` §5), then build.
- ❌ Assuming one physical press = one event. Cloud-mediated device events get coalesced;
  a trigger that fires 1 of 2 presses is worse than a documented limitation, so tell the
  user which buttons actually produced events and offer a more reliable bridge (Mi-Home
  automation toggling a device HA can see, or the vendor's HA integration).
- ❌ Shipping a text-only window when the user asked for a picture without saying so —
  state plainly which half works and what the remaining options are (device alarm images,
  official integration, adding a camera at that spot).
