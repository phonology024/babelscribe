# Desktop app (Windows, macOS, Linux)

A small window for making subtitles without a terminal ([#18](https://github.com/phonology024/babelscribe/issues/18)).
The code is in [`desktop/`](../desktop). It is not code-signed: Windows shows "unknown publisher" the first time, and
macOS asks you to confirm the first start (see below).

## What it does

1. **Choose a file**: drop a video or audio file on the window, or pick one. Recent files are listed.
2. **Options**: spoken language (or auto detect), accurate mode, **translate the subtitles** into another language with a
   model on this computer (Ollama, LM Studio or llama-server, found on their usual ports; *Check again* looks once
   more), **burn the subtitles into the video** in the *Plain*, *Karaoke* or *Shorts* look (the small pictures use the
   colours the engine really draws; an audio file has no picture, so the switch is off for it), which files to write
   (`.srt`, `.vtt`, `.txt`), and under *Advanced* names and terms to spell correctly, plus the same run as a command line.
   When the computer has too little free memory for the default model, the engine's note says which model is used
   instead ([memory.md](memory.md)).
3. **Working**: the real progress, step by step (transcribe, translate, burn), with an estimate of the time left.
   *Cancel* stops the run and every process it started (whisper-cli, ffmpeg).
4. **Result**: the subtitle lines (with a tab for the translation), the files written next to the input (the translated
   `.srt` and the video with captions included), *Open* and *Show in folder*.
5. **Connect to an AI app** (button at the top and in the sidebar): puts babelscribe into Claude Desktop, Claude Code,
   Codex CLI, Cursor or Gemini CLI, so that you can ask them for subtitles in plain words. See below.

Light and dark follow the system; the button at the top right switches. Everything runs on the computer; the network is
only used, as with the command line, to download whisper-cli and the model on first use.

## Connect to an AI app

The window starts `babelscribe-mcp`, the MCP server that ships inside the app (next to the engine: `babelscribe-mcp.exe`
in the install folder on Windows, `engine/babelscribe-mcp` in the app on macOS and Linux), so nothing else has to be
installed (no `uv`, no `uvx`, no Python). The work is done by the engine's own command, which you can also run in a
terminal: `babelscribe connect status | show APP | add APP | remove APP` (`--json`, `--no-backup`). `APP` is
`claude-desktop`, `claude-code`, `codex`, `cursor` or `gemini`. The rules:

- Before anything is changed the window shows **exactly what will be added** and to which file (or which command will run).
- A settings file is **merged, never replaced**: the other servers and settings stay, and so do the indentation and the
  line endings. The old file is copied to `NAME.bak` first (`NAME.bak2`, ... if that exists); the box can be unticked.
  The new content is checked before it replaces the file, and is written through a temporary file in the same folder.
- A file that has a **syntax error**, or is not the kind of file the app writes, is **left exactly as it is**, and the
  window says why and where (line and column). Nothing is changed, not even a backup is made.
- *Remove* takes out only the `babelscribe` entry (with a backup, too). *Copy instead, I'll add it myself* copies the text.
- Where it writes: Claude Desktop `claude_desktop_config.json` (Windows: the Store install keeps it in
  `%LOCALAPPDATA%\Claude-Data\claude_*\` (the most recently changed one if there are several), the same package has a
  `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\` copy, and the plain installer uses `%APPDATA%\Claude`; a file
  that exists wins in that order, else the folder of the first layout found; macOS `~/Library/Application Support/Claude`;
  Linux `~/.config/Claude`), Cursor `~/.cursor/mcp.json`, Gemini CLI `~/.gemini/settings.json` (with
  `"timeout": 3600000`, the one setting of this kind its documentation lists), Codex CLI `~/.codex/config.toml`
  (`$CODEX_HOME`; with `tool_timeout_sec = 3600` and `startup_timeout_sec = 120`, because its defaults of 60 and 10
  seconds are too short for a long video). Claude Code is set up with its own command, `claude mcp add --scope user
  babelscribe -- PROGRAM` (and `claude mcp remove`), run by the full path of the `claude` that was found (a `claude.cmd`
  from npm cannot be started by its bare name on Windows), so its own settings file is never edited by babelscribe.
  Claude Desktop and Cursor get only `command` and `args`.
- The command written into a config is the full path of `babelscribe-mcp` in the installed app. If you move or
  uninstall the app, connect again (or *Remove*).
- Apps are found by their program or their settings folder. Connect also works for an app that is not found (the file is
  created); Claude Code needs its `claude` command, and Codex's file needs the engine's Python 3.11+ (the app has it).

## Installing

`babelscribe-setup.exe` installs with one click: double-click it, a small window shows the progress, and babelscribe
starts when it is done. There are no questions to answer: it installs for the current user only, without admin rights,
into `%LOCALAPPDATA%\babelscribe`, with a Start menu shortcut and a desktop shortcut. The licences are in its `licenses`
folder. *Settings > Apps* lists it as "babelscribe" and uninstalls it completely. For scripts: `/S` installs silently
(add `/R` to start the app afterwards).

### macOS

`babelscribe-macos-arm64.dmg` is for Apple Silicon (macOS 14 or newer; the GPU is used through Metal),
`babelscribe-macos-x64.dmg` for Intel Macs (macOS 13 or newer; the CPU only, so it is slower). Open the `.dmg` and drag
babelscribe to Applications.

The app has no Apple Developer signature (that costs money per year), only the free ad-hoc one that Apple Silicon
needs to run it at all. The first time, macOS says it cannot check the app for malware. Open it anyway:

1. Try to open babelscribe once (double-click it in Applications). macOS refuses and offers *Done*.
2. Open *System Settings > Privacy & Security*, scroll down to the message about babelscribe and click *Open Anyway*,
   then confirm. (On macOS 14 and older you can instead right-click the app and choose *Open*.)

After that it opens like any other app. If macOS says the app is "damaged" after a download, remove the download mark
and open it again: `xattr -dr com.apple.quarantine /Applications/babelscribe.app`.

### Linux

`babelscribe-linux-x64.AppImage` runs on Ubuntu 22.04 or newer (and most distributions of the same age or newer): make
it executable (`chmod +x`) and run it. It needs FUSE 2 (`sudo apt install libfuse2` on Ubuntu 22.04 and 24.04); without
it, `APPIMAGE_EXTRACT_AND_RUN=1 ./babelscribe-linux-x64.AppImage` works. `babelscribe-linux-x64.deb` installs with
`sudo apt install ./babelscribe-linux-x64.deb` and puts babelscribe in the application menu. The program is called
`babelscribe-desktop`, so it does not take the place of the `babelscribe` command line if you installed that with pip.

The first run downloads the Vulkan build of whisper-cli (AMD, NVIDIA and Intel GPUs through the Vulkan driver). It
needs the Vulkan library, `libvulkan1`, which Ubuntu installs with its graphics drivers and the `.deb` depends on. On a
system without it (an AppImage on a minimal install) babelscribe says so once and uses the CPU build instead; install
`libvulkan1` and run it again to get the GPU. With no GPU driver the Vulkan build runs on the CPU.

The window uses WebKitGTK, whose DMA-BUF renderer leaves the window blank on some systems (NVIDIA drivers among them).
The app turns that renderer off itself (`WEBKIT_DISABLE_DMABUF_RENDERER=1`, unless you have set the variable).

### Which whisper-cli is downloaded on first use

The same choice the command line makes (`babelscribe/backend.py`): Windows and Linux x64 get the Vulkan build, Apple
Silicon the Metal build, Intel Macs the CPU build. Each download is checked against a pinned SHA-256 before it is run.

## How it is built

- **Window**: [Tauri 2](https://tauri.app) with React, TypeScript, Vite, Tailwind CSS and components adapted from
  shadcn/ui. The Poppins font is bundled, so nothing is fetched at run time. Licences: `desktop/THIRD-PARTY-NOTICES.md`.
- **Engine**: the standalone `babelscribe` from `packaging/standalone` (PyInstaller, built on each system it is
  for), named `babelscribe-engine` inside the app. The window runs it as `babelscribe FILE ... --progress-json` and
  reads one JSON event per line from it (`log`, `progress`, `done`, `error`; see [usage.md](usage.md)). All
  transcription logic stays in the Python package; the Rust side (`desktop/src-tauri/src/main.rs`) only starts and
  stops the engine, opens the file picker, reads the written subtitles back and opens files and folders.
  - Where it is: on Windows a Tauri sidecar next to the app with its `_internal` folder beside it (as before); on
    macOS and Linux the whole engine folder is a resource, `engine/babelscribe-engine` with `engine/_internal`
    (`Contents/Resources` in the `.app`, `usr/lib/babelscribe` in the AppImage and the `.deb`), because a sidecar and
    the resources end up in different folders there. The per-system settings are in
    `desktop/src-tauri/tauri.{windows,macos,linux}.conf.json`.
  - Stopping it: *Cancel*, closing the window, Quit from the menu or the Dock, all end the engine **and what it
    started** (whisper-cli, ffmpeg). Windows: `taskkill /T`. macOS and Linux: the engine is started as the leader of
    its own process group and the group gets SIGTERM, then SIGKILL after two seconds.
  - If the app itself is killed or crashes it cannot clean up, so the engine does it: the app starts it with
    `--exit-when-stdin-closes` and a pipe on its standard input that it holds open and never writes to. When the app
    ends, however it ends, the system closes the pipe, and the engine stops whisper-cli and ffmpeg and exits (the
    same on all three systems; see `babelscribe/lifecycle.py`).
  - On Linux the engine starts whisper-cli and ffmpeg with the library path the app was started with, not the
    PyInstaller folder's (`packaging/standalone/frozen_env.py`): the GPU driver whisper-cli loads must not run against
    the libraries the engine was built with.
- **AI apps and local models**: the window never touches an app's files itself. It runs `babelscribe connect ... --json`
  and `babelscribe llms --json` (which local models answer), `babelscribe models --json` (what fits this computer's
  memory), and shows the answers; the rules and the words are in the engine, `babelscribe/connect.py`. The app ships both
  programs of the standalone build, `babelscribe-engine` and `babelscribe-mcp`, which share one `_internal` folder.
- **Logo and icons**: a rounded square with a lowercase "b" in Poppins SemiBold, as outlines (`desktop/src-tauri/icons/logo.svg`).
  `desktop/scripts/make_icons.py` draws every icon size from it (the small ones on the pixel grid, with a heavier "b")
  and the installer pictures, and the same mark for the website, the `.mcpb` bundle and the Claude plugin; the Square*Logo files come from `npx @tauri-apps/cli@2.12.6 icon icons/icon-source.png`.
- **Installers**: macOS `.dmg` (ad-hoc signed, `signingIdentity "-"`), Linux `.AppImage` and `.deb`, both built on
  Ubuntu 22.04 so they run on it and on newer systems. Windows: Tauri's NSIS installer with its own template, `desktop/src-tauri/installer/installer.nsi`: Tauri's
  template with the changes listed at its top (one click; a single dark progress window with the logo, a slim
  gold bar and no buttons; start the app afterwards; remove every folder on uninstall).
- **CI**: [`.github/workflows/desktop.yml`](../.github/workflows/desktop.yml) builds the engine the same way as the
  standalone build, builds the app and its installer, installs it, runs one real transcription through the installed
  engine, starts the app and checks it stays up, and keeps the installers as workflow artifacts. It runs when
  `desktop/`, the Python package or the standalone recipe change.
  - `windows-latest`: installs the NSIS installer silently and checks the files, the Start menu shortcut and the *Apps*
    entry, uninstalls it silently and checks that nothing is left, installs it once more the way a double-click does
    (with screenshots).
  - `macos-15` (Apple Silicon) and `macos-15-intel`: mounts the `.dmg`, copies the app to `/Applications`, verifies
    the ad-hoc signature, starts the app and quits it the way Cmd+Q does.
  - `ubuntu-22.04`: `apt install` of the `.deb` and its dependencies, the AppImage (unpacked, and started), the app
    under Xvfb with a window manager, closed the way a window is closed.
  - On all three systems `desktop/scripts/check_connect.py` runs the *installed* engine against a fake home folder: it
    adds babelscribe to Claude Desktop, Cursor, Gemini CLI and Codex configs that already hold other things, and
    requires that the other things stay, the old file is kept byte for byte as `.bak`, remove takes out only
    babelscribe, a config with a syntax error is refused and left untouched, and the command that was written really
    starts and answers an MCP handshake with the `transcribe` tool.
  - On macOS and Linux a Rust test also starts the *installed* engine on an 11-minute recording, stops it as the app
    does while whisper-cli is working, and checks that no process of its group is left. On all three systems a script
    plays the app (a pipe on the engine's standard input, a long recording), kills it outright once whisper-cli is
    running, and checks that the engine and whisper-cli are gone within 20 seconds. What CI cannot do is click in
    the window: the start of a transcription from the window, Cmd+Q during one, and what macOS shows on the first start
    of an app downloaded from the internet are not tested.

## Working on it

The window can be developed in a browser with a stand-in engine (no Rust, no GPU, nothing transcribed):

```bash
cd desktop
npm install
npm run dev        # http://localhost:1420 ; ?demo=1..4 shows each screen with sample data, ?theme=dark|light
npm test           # unit tests: arguments, progress events, subtitle parsing, recent files
npm run build      # type check + production build of the window
```

Building the app itself needs Rust and the engine in place. Windows:

```bash
pip install . pyinstaller
pyinstaller --noconfirm --distpath dist --workpath build packaging/standalone/babelscribe.spec
mkdir -p desktop/src-tauri/binaries desktop/src-tauri/engine
cp dist/babelscribe/babelscribe.exe desktop/src-tauri/binaries/babelscribe-engine-x86_64-pc-windows-msvc.exe
cp -r dist/babelscribe/_internal desktop/src-tauri/engine/_internal
cd desktop && npx tauri dev       # or: npx tauri build  -> src-tauri/target/release/bundle/nsis/*-setup.exe
```

macOS and Linux (on Linux first install WebKitGTK and the other libraries of the
[Tauri prerequisites](https://v2.tauri.app/start/prerequisites/#linux)):

```bash
pip install . pyinstaller
pyinstaller --noconfirm --distpath dist --workpath build packaging/standalone/babelscribe.spec
mkdir -p desktop/src-tauri/engine
cp dist/babelscribe/babelscribe desktop/src-tauri/engine/babelscribe-engine
cp -R dist/babelscribe/_internal desktop/src-tauri/engine/_internal
cd desktop && npx tauri dev       # or: npx tauri build  -> .dmg, or .AppImage and .deb, under src-tauri/target/release/bundle/
```
