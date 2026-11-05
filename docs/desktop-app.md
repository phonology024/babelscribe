# A small desktop app: design proposal

Discussion for [#18](https://github.com/phonology024/babelscribe/issues/18), which asks for *"a tiny GUI (tkinter, Tauri
or similar — your pick, keep install small) wrapping `api.transcribe_file`"* and says it is *"open for design discussion
first"*. This is the discussion, not an implementation.

The constraints from the issue are **tiny** and **keep install small**, so the proposal is judged mostly on what it adds
to an install, and on whether it can ship without a build toolchain.

---

## Recommendation

**tkinter, in the package, as `babelscribe gui`.** It is the only option that adds **zero bytes** to the install and
needs no compiler, bundler or release pipeline.

What that costs: it looks like a 1995 application, and macOS ships Tk 8.5.9 with `/usr/bin/python3`, which renders badly.
On a modern Python (python.org 3.11+ ships Tk 8.6.12, and uv's python-build-standalone includes `tkinter`) it is
perfectly usable. Verified on this machine: Tk 8.6.12 opens a window; Apple's 3.9 opens 8.5.9.

---

## Options

| | **tkinter** | **Tauri** | **Electron** | **PySide6 / Qt** | **native (Swift/C#)** |
|---|---|---|---|---|---|
| Added install | **0 bytes** (stdlib) | ~3 MB app + 40–100 MB WebView | ~150 MB | ~80–120 MB | 0 (needs a per-OS toolchain) |
| Extra runtime for users | none | system WebView | bundles Chromium | Qt libs | none |
| Build toolchain needed | **none** | Rust + Node + per-OS signing | Node | none for a wheel | Xcode / MSVC |
| Per-OS work | one `.py` | build + sign per OS | build per OS | one wheel, per-OS wheels | one app per OS |
| Looks | dated | modern | modern | modern | native |
| Ships from PyPI as part of `pip install babelscribe` | **yes** | no | no | yes (but heavy) | no |
| Effort | ~1 day | ~1 week + CI work | ~3 days | ~3 days | weeks × 3 |

**Tauri/Electron are ruled out by the issue's own constraint.** They would turn a `pip install` into a download of a
signed binary per OS, and this project currently has no app-release pipeline at all — introducing code signing, macOS
notarisation and a Windows installer for a feature described as "tiny" is out of proportion. Tauri's output is small
*for a desktop app*, but it is not small next to a zero-byte option.

**Qt is the middle ground** if the dated look is a blocker: a PySide6 wheel is ~80 MB, dwarfs the 11 MB dependency
footprint of the whole rest of the project, and still needs no build step.

---

## What the app has to do

The API already does the work, so the GUI is a thin shell over `api.transcribe_file`. The only genuinely new thing is
progress, and that needs a small API-adjacent addition.

### Progress needs one small change

`transcribe_file` accepts a `log` callback, but today it is called only 5 times per run — before and after the work, not
during it. A window with a static "transcribing…" label for 10 minutes is a bad app.

whisper-cli has `-pp/--print-progress`, which prints real percentages. Measured on the 5-minute file:

```
12 updates over 10.3 s — (1.4 s, 9%) … (10.3 s, 100%), roughly every 0.8 s
```

A prototype of the actual wiring — `Popen` with `stderr=PIPE`, parse `progress = N%`, keep `-ojf` JSON output — was run
against the same 5-minute file: **11 live updates**, returncode 0, and the JSON still parses with 62 segments. So the
approach works and does not disturb the existing output path.

That is enough to drive a real progress bar. Wiring it up needs `transcribe.run` to accept an `on_progress` callback and
stream stderr instead of `capture_output`, then pass it through `api.transcribe_file` as a new keyword argument — a
minor-version addition under `API_STABILITY.md`, which is allowed.

Critically, **the GUI must run the work on a worker thread**. `transcribe_file` blocks, and calling it on the Tk thread
freezes the window — the classic mistake with this design.

### Screen flow

One window, one screen — not a wizard:

```
┌──────────────────────────────────────────────────────────┐
│ babelscribe                                              │
├──────────────────────────────────────────────────────────┤
│ File:  [ /Users/me/talks/keynote.mp4            ] [ … ]  │
│                                                          │
│ Language: [ auto ▾ ]   Model: [ turbo ▾ ]                │
│ ☐ Accurate (slower, fewest errors)                      │
│ ☑ Subtitles (.srt)  ☐ Text (.txt)  ☐ WebVTT  ☐ JSON     │
│                                                          │
│ Device:  metal Apple GPU (auto)                          │
│                                                          │
│ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░  58%   ~12 s left                 │
│ Transcribing with turbo on metal Apple GPU…              │
│                                                          │
│ [ Transcribe ]  [ Open folder ]                          │
└──────────────────────────────────────────────────────────┘
```

- Drag and drop if the platform allows; otherwise a normal file picker. Tk has no drag-and-drop in the stdlib, so on
  macOS this would need `tkinterdnd2` (~1 MB) — worth skipping for v1.
- Language defaults to `auto`; accurate mode is a checkbox, not a separate mode.
- The device list comes from `api.setup(...)`, cached at startup so opening the window is instant and the GPUs are
  visible before the user commits.
- On success it shows the written paths and a button that reveals them in Finder/Explorer. Never a modal success dialog.
- On failure it shows the exception message in the window, not a traceback — `transcribe_file` already produces good
  messages ("no such file", "no device 5; available: …").

### What it should not do

- **No batch queue.** `find_media` + a folder picker is a separate, later feature; a queue is most of the complexity of
  a real app and none of its value for v1.
- **No editing.** Proofreading subtitles in a GUI is a text-editor problem.
- **No model management screen.** The first run downloads 1.6 GB; say so in the status line and let it happen.
- **No tray icon, no auto-update, no telemetry.**

---

## Platform notes

- **Linux**: `python3-tk` is a *separate* package on Debian/Ubuntu (`apt install python3-tk`). The app must detect a
  missing tkinter and print "install python3-tk" rather than crash with `ImportError`. The AUR package already depends
  on `python`; `tk` would become an `optdepends`.
- **macOS**: works with python.org and uv pythons. Apple's `/usr/bin/python3` has Tk 8.5.9 and looks wrong; the message
  should point at `pip install`'s interpreter, not the system one.
- **Windows**: python.org installers include Tk; nothing extra. The winget/Scoop manifests in #21 would not need changes.
- **Headless/SSH**: importing `tkinter` succeeds but `Tk()` raises without a display. `babelscribe gui` should catch that
  and say "no display; use the command line".

## Suggested scope for a first PR

1. `transcribe.run(..., on_progress=)` + `transcribe_file(..., on_progress=)` — useful to the MCP server too, which can
   then report progress properly instead of a single call.
2. `babelscribe/gui.py` with the single window above, run on a worker thread.
3. `babelscribe gui` subcommand, and a "GUI" line in the README.
4. Tests: the progress-callback parsing (feed it captured stderr), and that `gui` exits cleanly with no display. The
   window itself is not worth a headless test; one manual screenshot in the PR is more valuable.

Estimated: **~1 day**, most of it the progress streaming and threading rather than the widgets.

## Open questions for the maintainer

1. **tkinter's look acceptable, or is Qt's ~80 MB worth it?** This is the one decision that changes the recommendation.
2. Should `babelscribe gui` be **part of the main package** (0 bytes, always available) or a separate `babelscribe[gui]`
   extra? I lean toward the main package — a GUI nobody can find is worse than one that ships by default.
3. Is a **folder/batch mode** wanted soon enough that the design should leave room for it now?