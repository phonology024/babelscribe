# Setting up babelscribe for someone (for AI coding assistants)

These are steps an AI assistant with a terminal (Claude Code, Codex CLI, Gemini CLI, OpenCode, Cursor, ...) can follow to
install babelscribe for the person it works for, connect it to their AI app and check that it works. People can follow
them too. Back to the [README](../README.md).

## Rules
- **Ask before** you install anything, change an AI app's settings, start a download of more than a few MB, or delete
  anything. Say what will happen and how big it is.
- Do not use `sudo` or an administrator prompt without asking. babelscribe itself needs neither.
- Do not turn off a security warning or a certificate check for the person. Explain the warning and let them decide.
- babelscribe works on files on this computer. Do not upload the person's audio, video or transcripts anywhere.

## 1. Choose: the desktop app or the command line
- Someone who does not use a terminal: the **desktop app** (step 2).
- Someone who wants commands, Python, or babelscribe inside an AI app and has Python: the **command line** (step 3).

Both can do the Connect step. You only need one.

## 2. Desktop app
Take the file for their system from the
[latest release](https://github.com/phonology024/babelscribe/releases/latest). If the release has no desktop files,
use the command line instead.

| System | File |
|---|---|
| Windows 10 or 11 (x64) | `babelscribe-setup.exe` |
| Mac with Apple Silicon, macOS 14 or newer | `babelscribe-macos-arm64.dmg` |
| Intel Mac, macOS 13 or newer (CPU only, slower) | `babelscribe-macos-x64.dmg` |
| Linux x64, Ubuntu 22.04 or newer | `babelscribe-linux-x64.deb`, or `babelscribe-linux-x64.AppImage` |

The app is not code-signed, so the system warns the first time. The person clicks through it themselves:
- Windows: *More info*, then *Run anyway*.
- macOS: try to open it once, then *System Settings > Privacy & Security > Open Anyway*.

Installation details (silent install, FUSE for the AppImage, `libvulkan1`): [desktop-app.md](desktop-app.md#installing).
The app holds its own engine, so it needs no Python. To connect it to an AI app, the person presses
*Connect to an AI app* in the window, or you run the installed engine (`babelscribe-engine`, in the app's folder; on
Windows `%LOCALAPPDATA%\babelscribe\babelscribe-engine.exe`) with the `connect` commands of step 5.

## 3. Command line
Check Python first: `python --version` (or `python3 --version`). babelscribe needs **3.9 or newer**; its MCP server,
which AI apps use, needs **3.10 or newer**. Then install with whichever of these the computer already has:

```bash
pipx install babelscribe          # or:  uv tool install babelscribe
pip install babelscribe           # inside a virtual environment
```
If pip answers `externally-managed-environment` (recent Linux and Homebrew Python), use `pipx`, `uv` or a virtual
environment. Do not use `--break-system-packages`.

ffmpeg comes with it, and there is nothing to compile.

## 4. Check that it works
```bash
babelscribe --version
babelscribe doctor                # downloads nothing: memory, ffmpeg, disk space, whisper-cli if it is already there
```
A real test needs a download the first time: `whisper-cli` (about 35 MB on Windows with Vulkan; the Linux CUDA build is
about 800 MB) and a model.
With the smallest model, `tiny` (75 MB):

```bash
babelscribe devices -m tiny       # lists the GPUs whisper.cpp sees; the line "auto picks device N" is the one used
curl -sSfLO https://github.com/ggml-org/whisper.cpp/raw/v1.9.4/samples/jfk.wav     # 11 s, public domain
babelscribe jfk.wav -m tiny -l en -f txt
```
It works when `jfk.txt` holds the sentence with "ask not what your country can do for you". Delete `jfk.wav` and
`jfk.txt` afterwards. Without `-m`, babelscribe uses `turbo` (1.6 GB, downloaded the first time), or a smaller model
when free memory is short. An interrupted download continues when the command is run again.

For the fewest errors in **Thai or Hindi**, `--accurate` needs a fine-tune that is converted once. Ask first: it means
`pip install "babelscribe[finetune]"` (torch, several hundred MB or more), a download of about 3 GB (Thai) or 6 GB
(Hindi) and a lot of memory while converting (about 10 GB for Thai). Without it babelscribe uses large-v3 and says so.

## 5. Connect it to their AI app (MCP)
```bash
babelscribe connect status                # which apps are on this computer, and whether babelscribe is in each
babelscribe connect show claude-code      # exactly what would be added; changes nothing
babelscribe connect add claude-code       # after the person agrees
```
`APP` is `claude-desktop`, `claude-code`, `codex`, `cursor`, `gemini` or `opencode` (OpenCode 2 or newer). A settings
file is merged, not replaced, and a `.bak` copy is kept. With Python older than 3.11, `codex` can only be shown: add the
shown text to the file. If the command refuses, report its message as it is; do not edit around it.

For an app that is not in the list, add an MCP server that runs `babelscribe mcp` (stdio). Use the full path of
`babelscribe` if the app does not find it, and set the app's tool time limit to an hour if it has one. Examples are in
the [README](../README.md#use-it-from-an-ai-app-mcp--no-terminal-needed).

**Check:** the person quits the AI app completely and opens it again (a running session does not pick up a new server;
that includes your own, if you connected yourself). The app should list a `babelscribe` server with a `transcribe` tool
(`/mcp` in Claude Code, Codex CLI and Gemini CLI; `opencode mcp list` for OpenCode). Then they can ask: *"make subtitles
for the newest video in my Downloads"*.

## 6. Optional: translation into other languages
English comes from whisper itself (`--translate`). Other languages need a model running on this computer (Ollama,
LM Studio, llama-server, colibri). `babelscribe llms` shows what answers. Do not install one without asking.

## If a step fails
[troubleshooting.md](troubleshooting.md) lists the messages and what to do. `babelscribe doctor` ends with a report for
an issue; read it before it is posted, because it holds folder names from this computer.

## Removing it
Ask first, and keep this order:
```bash
babelscribe connect remove --all          # takes babelscribe out of the AI apps it was connected to
pipx uninstall babelscribe                # or: uv tool uninstall babelscribe  /  pip uninstall babelscribe
```
Downloaded programs and models stay in `~/.babelscribe` (or where `BABELSCRIBE_HOME` / `BABELSCRIBE_MODELS` point).
Delete that folder only if the person wants the space back. The desktop app is removed like any app; on macOS and Linux
press *Remove* in its Connect window first.
