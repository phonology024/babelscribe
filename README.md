# babelscribe — free, offline speech-to-text and subtitles on any GPU (AMD, NVIDIA, Intel, Apple)

<!-- mcp-name: io.github.phonology024/babelscribe -->

[![PyPI](https://img.shields.io/pypi/v/babelscribe)](https://pypi.org/project/babelscribe/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP server](https://img.shields.io/badge/MCP-server-blue)](#use-it-from-an-ai-app-mcp--no-terminal-needed)
**Translations:** [తెలుగు (Telugu)](README.te.md)

**babelscribe turns any audio or video file into subtitles (SRT, VTT) and text, in any of Whisper's 99 languages, on your
own graphics card — AMD Radeon, NVIDIA, Intel Arc or Apple Silicon — or the CPU. No CUDA needed, no cloud, free (MIT).**
It runs OpenAI Whisper through [whisper.cpp](https://github.com/ggml-org/whisper.cpp) with Vulkan, CUDA or Metal, and works
from the command line, from Python, or from AI apps (Claude, Codex, Antigravity, Gemini CLI, Cursor) as an MCP server.

## Install
```bash
pip install babelscribe          # Python 3.9+
```
On first use babelscribe downloads a prebuilt `whisper-cli` for your system (Vulkan, CUDA, Metal or CPU), so there is
nothing to compile. Which build your hardware gets: [How it works](https://github.com/phonology024/babelscribe/blob/main/docs/usage.md#how-it-works).
Docker: [docs/usage.md#docker](https://github.com/phonology024/babelscribe/blob/main/docs/usage.md#docker).

## Quick start
```bash
babelscribe interview.mp4                 # auto-detects language, picks your best GPU -> interview.srt + interview.json
babelscribe talk.mp4 -f srt,vtt,txt,json  # all formats
babelscribe ./recordings -o ./subs --skip-existing   # a whole folder; leave files that are already done
babelscribe talk.mp4 -l th --accurate     # slower, fewest errors (best model per language)
babelscribe clip.mp4 --burn --style shorts   # also clip.subbed.mp4: the video with the captions drawn on
```
All options, Python, translation, burn-in and re-export:
[docs/usage.md](https://github.com/phonology024/babelscribe/blob/main/docs/usage.md).

## Use it from an AI app (MCP) — no terminal needed

[![babelscribe MCP server](https://mcprush.com/badge/babelscribe-mcp/card.svg)](https://mcprush.com/to/babelscribe-mcp?ref=badge)

babelscribe is also an [MCP](https://modelcontextprotocol.io) server, so any AI app that supports local MCP servers can
transcribe files on **your** computer with **your** GPU. Ask in plain words — *"make Thai subtitles for the newest video in
my Downloads"* — and the app finds the file, transcribes it, writes `.srt` / `.txt` next to it, and can then proofread names,
translate or summarise the text for you.

Tools: `transcribe`, `transcribe_folder`, `convert_subtitles`, `burn_subtitles`, `translate_subtitles`, `find_media`,
`list_devices`, `list_languages_and_models`. What each one does:
[docs/usage.md#mcp-tools](https://github.com/phonology024/babelscribe/blob/main/docs/usage.md#mcp-tools).

**Claude Desktop (one click):** download `babelscribe.mcpb` from the [latest release](https://github.com/phonology024/babelscribe/releases/latest)
and double-click it (or *Settings → Extensions → Install extension*).

**Everything else** runs the same command — [uv](https://docs.astral.sh/uv/) fetches babelscribe for you:
`uvx babelscribe mcp`

| App | How to add it |
|---|---|
| Claude Code | `claude mcp add babelscribe -- uvx babelscribe mcp` |
| OpenAI Codex CLI | `codex mcp add babelscribe -- uvx babelscribe mcp`, then in `~/.codex/config.toml` under `[mcp_servers.babelscribe]` set `tool_timeout_sec = 3600` and `startup_timeout_sec = 120` (defaults are 60 s / 10 s — too short for a long video or the first model download) |
| Google Antigravity | agent panel → ⋯ → *MCP Servers* → *Manage MCP Servers* → *View raw config*, add the JSON below |
| Gemini CLI | add the JSON below to `~/.gemini/settings.json` |
| Cursor | add the JSON below to `~/.cursor/mcp.json` |
| VS Code (Copilot) | `.vscode/mcp.json`: same entry under `"servers"` with `"type": "stdio"` |

```json
{
  "mcpServers": {
    "babelscribe": { "command": "uvx", "args": ["babelscribe", "mcp"], "timeout": 3600000 }
  }
}
```
(`timeout` is in milliseconds and only some apps read it.) Already installed with pip? Use `"command": "babelscribe", "args": ["mcp"]`.
Web-only chat apps (e.g. grok.com, chatgpt.com) can only reach servers on the internet, not your computer, so they can't use your GPU or files.

## Results
GPU: AMD Radeon RX 9070 XT via Vulkan. *default* = `large-v3-turbo`; *accurate* = `--accurate`.

| Test | default | `--accurate` |
|---|---|---|
| English TED talk, 19.3 min, WER vs human captions | 48 s (24x) · 1.5% | 107 s (11x) · 1.5% |
| Thai, Google FLEURS, CER | 15.9% | 8.9% |
| Hindi, Google FLEURS, WER | 28.4% | 12.6% |
| English, Google FLEURS, WER | 6.1% | 5.7% |

FLEURS: 50 utterances per language. All 16 languages, four TED / TEDx talks, method and the models that were tried and
not used: [docs/benchmarks.md](https://github.com/phonology024/babelscribe/blob/main/docs/benchmarks.md).

## Languages
All 99 languages Whisper was trained on, auto-detected or forced with `-l`. For Thai and Hindi, `--accurate` uses a
community fine-tune. The full list and how to add a fine-tune:
[docs/languages.md](https://github.com/phonology024/babelscribe/blob/main/docs/languages.md).

## ภาษาไทย
ใช้ผ่าน Claude Desktop ได้โดยไม่ต้องพิมพ์คำสั่ง: โหลด `babelscribe.mcpb` จากหน้า Releases แล้วดับเบิลคลิก จากนั้นพิมพ์ในแชทว่า *"ทำซับไทยให้คลิปล่าสุดในโฟลเดอร์ดาวน์โหลด"*
ถอดเสียงจากไฟล์เสียงหรือวิดีโอได้ทุกภาษา บนการ์ดจอทุกยี่ห้อ (AMD / NVIDIA / Intel ผ่าน Vulkan, Apple ผ่าน Metal) หรือ CPU
ภาษาไทยแนะนำ `babelscribe ไฟล์.mp4 -l th --accurate` — ข้อความจาก Pathumma Whisper (NECTEC) ที่ผิดน้อยที่สุดใน FLEURS (CER 8.9% เทียบ turbo 15.9%) + เวลาจาก large-v3-turbo
หรือเลือก Thonburian Whisper เอง: `--text-model thai-thonburian`

## More docs
- [Usage](https://github.com/phonology024/babelscribe/blob/main/docs/usage.md): features, every command, Python, MCP tools, Docker, prebuilt binaries
- [Benchmarks](https://github.com/phonology024/babelscribe/blob/main/docs/benchmarks.md): TED talks and 16 languages on FLEURS
- [FAQ](https://github.com/phonology024/babelscribe/blob/main/docs/faq.md): common questions, limitations, how it compares
- [Languages](https://github.com/phonology024/babelscribe/blob/main/docs/languages.md): all 99 languages, adding a fine-tune
- [Roadmap](https://github.com/phonology024/babelscribe/blob/main/ROADMAP.md) and [open issues](https://github.com/phonology024/babelscribe/issues)
- [Contributing](https://github.com/phonology024/babelscribe/blob/main/CONTRIBUTING.md) · [Changelog](https://github.com/phonology024/babelscribe/blob/main/CHANGELOG.md)

## Privacy Policy
babelscribe runs entirely on your own computer. It has no telemetry, analytics, accounts or crash reporting, and never
uploads your audio, video, transcripts or file names. The network is used only to download `whisper-cli`, models and
Python packages. Optional translation (`--translate-to`) sends subtitle text only to an LLM on this computer, unless you
pass `--allow-remote`. Full policy: [docs/privacy.md](https://github.com/phonology024/babelscribe/blob/main/docs/privacy.md).

## Credits & licence
MIT. Built on [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (MIT) and OpenAI Whisper models (MIT).
Fine-tunes belong to their authors: [Pathumma Whisper](https://huggingface.co/nectec/Pathumma-whisper-th-large-v3) by NECTEC,
[Thonburian Whisper](https://huggingface.co/biodatlab/whisper-th-large-v3-combined) by biodatlab,
[whisper-hindi-large-v2](https://huggingface.co/vasista22/whisper-hindi-large-v2) by vasista22 (Speech Lab, IIT Madras).
