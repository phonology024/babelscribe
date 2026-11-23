# Desktop app (Windows)

A small window for making subtitles without a terminal ([#18](https://github.com/phonology024/babelscribe/issues/18)).
The code is in [`desktop/`](../desktop). It is unsigned, so Windows shows "unknown publisher" the first time.

## What it does

1. **Choose a file**: drop a video or audio file on the window, or pick one. Recent files are listed.
2. **Options**: spoken language (or auto detect), accurate mode, which files to write (`.srt`, `.vtt`, `.txt`), and
   under *Advanced* names and terms to spell correctly, plus the same run as a command line.
3. **Working**: the real progress of the transcription, with an estimate of the time left. *Cancel* stops the run and
   every process it started (whisper-cli, ffmpeg).
4. **Result**: the subtitle lines, the files written next to the input, *Open* and *Show in folder*.

Light and dark follow Windows; the button at the top right switches. Everything runs on the computer; the network is
only used, as with the command line, to download whisper-cli and the model on first use.

## Installing

`babelscribe-setup.exe` installs with one click: double-click it, a small window shows the progress, and babelscribe
starts when it is done. There are no questions to answer: it installs for the current user only, without admin rights,
into `%LOCALAPPDATA%\babelscribe`, with a Start menu shortcut and a desktop shortcut. The licences are in its `licenses`
folder. *Settings > Apps* lists it as "babelscribe" and uninstalls it completely. For scripts: `/S` installs silently
(add `/R` to start the app afterwards).

## How it is built

- **Window**: [Tauri 2](https://tauri.app) with React, TypeScript, Vite, Tailwind CSS and components adapted from
  shadcn/ui. The Poppins font is bundled, so nothing is fetched at run time. Licences: `desktop/THIRD-PARTY-NOTICES.md`.
- **Engine**: the standalone `babelscribe.exe` from `packaging/standalone` (PyInstaller), shipped inside the app as a
  Tauri sidecar named `babelscribe-engine.exe`. The window runs it as `babelscribe FILE ... --progress-json` and reads
  one JSON event per line from it (`log`, `progress`, `done`, `error`; see [usage.md](usage.md)). All transcription
  logic stays in the Python package; the Rust side (`desktop/src-tauri/src/main.rs`) only starts and stops the engine,
  opens the file picker, reads the written subtitles back and opens files and folders.
- **Logo and icons**: a rounded square with a lowercase "b" in Poppins SemiBold, as outlines (`desktop/src-tauri/icons/logo.svg`).
  `desktop/scripts/make_icons.py` draws every icon size from it (the small ones on the pixel grid, with a heavier "b")
  and the installer pictures, and the same mark for the website, the `.mcpb` bundle and the Claude plugin; the Square*Logo files come from `npx @tauri-apps/cli@2.12.6 icon icons/icon-source.png`.
- **Installer**: Tauri's NSIS installer with its own template, `desktop/src-tauri/installer/installer.nsi`: Tauri's
  template with the changes listed at its top (one click; a single dark progress window with the logo, a slim
  gold bar and no buttons; start the app afterwards; remove every folder on uninstall).
- **CI**: [`.github/workflows/desktop.yml`](../.github/workflows/desktop.yml) builds the engine the same way as the
  standalone build, builds the app and its NSIS installer on `windows-latest`, then installs it silently and checks the files,
  the Start menu shortcut and the *Apps* entry, runs one real transcription through the installed engine, starts the
  app, uninstalls it silently and checks that nothing is left, installs it once more the way a double-click does
  (with screenshots), and keeps `babelscribe-setup.exe` as a workflow artifact. It runs when `desktop/`, the Python package or the standalone recipe change.

## Working on it

The window can be developed in a browser with a stand-in engine (no Rust, no GPU, nothing transcribed):

```bash
cd desktop
npm install
npm run dev        # http://localhost:1420 ; ?demo=1..4 shows each screen with sample data, ?theme=dark|light
npm test           # unit tests: arguments, progress events, subtitle parsing, recent files
npm run build      # type check + production build of the window
```

Building the app itself needs Rust and the engine in place:

```bash
pip install . pyinstaller
pyinstaller --noconfirm --distpath dist --workpath build packaging/standalone/babelscribe.spec
mkdir -p desktop/src-tauri/binaries desktop/src-tauri/engine
cp dist/babelscribe/babelscribe.exe desktop/src-tauri/binaries/babelscribe-engine-x86_64-pc-windows-msvc.exe
cp -r dist/babelscribe/_internal desktop/src-tauri/engine/_internal
cd desktop && npx tauri dev       # or: npx tauri build  -> src-tauri/target/release/bundle/nsis/*-setup.exe
```
