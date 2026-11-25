# Diagnosing a voice/audio message the user says arrived broken

Class: "your mp3 failed", "发送错误", a play button that won't play, or a card note like
`Couldn't fetch <name> from the gateway (missing, unreadable, or too large)`.

Work the proof order — cheapest and most decisive first. Do not open with the UI, the gateway,
or the channel: none of them can see whether the file was ever created.

## 1. Did the generation actually happen?

Read the turn out of the session DB instead of trusting the conversation summary or your own
memory of it:

```python
import sqlite3
c = sqlite3.connect('$HERMES_HOME/state.db')          # Windows: %LOCALAPPDATA%/hermes/state.db
rows = c.execute("""select id, role, tool_name, tool_calls, timestamp
                    from messages where session_id=? and id>=? order by id""", (sid, start_id))
```

- a `text_to_speech` **tool** row = the tool really ran;
- an assistant row carrying **no `tool_calls`** = nothing was generated, whatever the message
  text claims. That is the whole answer; stop here and own it.

## 2. Log signature

```bash
grep -n "tts_" logs/agent.log
```

Every successful generation writes `tools.tts_tool: TTS audio saved: <path> (<bytes> bytes,
provider: …)` (twice per call, once per line). No line for the timestamp in question ⇒ no file
was ever written. This is the fastest cross-check for step 1.

## 3. Disk, including the realpath

`ls -la` the returned path, then check the parent directories with `ls -ld`: a profile cache dir
can be a symlink/junction onto another drive, so the same file legitimately has two path forms.
A symlinked cache is a *suspect*, never a verdict — say so instead of writing it up as the cause.

## 4. Integrity of the audio itself

```bash
ffprobe -v error -show_entries format=duration,format_name,bit_rate -of default=nw=1 <file>
ffmpeg  -v error -i <file> -f null -        # silent output = decodes clean
```

A file that probes clean is not the problem; move to step 5 rather than re-encoding anything.

## 5. App side (Hermes desktop)

In local connection mode an audio artifact is played through `hermes-media://stream/<encoded
path>`; the Electron main process reads the file off disk, so from the app's side every failure
is "missing, unreadable, or too large". Check `logs/desktop.log` at that timestamp (renderer
`[renderer console:main]` lines are captured there), but **absence of an error there is not
proof of success** — the card's failure state can be purely client-side.

## 6. When you still cannot see it

Packaged builds expose no CDP port, so the user's live DOM is not readable; do not pretend a
code-reading exercise is an observation of their screen. Ask for the exact error text or a
screenshot, and state plainly which parts are proven and which are hypotheses. When a path-shape
problem is suspected, a controlled comparison — the same bytes placed at two different path
form, one card each — beats another round of speculation.

**Run that comparison before blaming path shape.** When both forms play for the user, path shape is
*exonerated*: the original failure was a moment-in-time one (app restart / update window / transient
read), not the path, the symlink, or the encoding. Say "could not reproduce; path and encoding are
ruled out" and stop chasing it — and do not write the symlink up as the cause in any doc.
Also note a card's failed state does not self-heal: a `<audio>` element that errored once will not
retry on its own, so the cheapest next question is "does the ORIGINAL card still show the error,
or does it play now?" — that separates "transient" from "broken".

## Report shape

Verdict first (whose problem it is: fabricated path, real file that failed to render, or the app),
then a per-message evidence table (tool call? log line? file? integrity?), then the single next
diagnostic step. No narrative of the digging.
