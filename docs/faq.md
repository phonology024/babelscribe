# FAQ

Back to the [README](../README.md).

**How do I run Whisper on an AMD GPU on Windows?**
`pip install babelscribe`, then `babelscribe video.mp4`. It downloads a Vulkan build of whisper.cpp that runs on AMD Radeon
(and Intel Arc / NVIDIA) cards on Windows and Linux — no ROCm, no CUDA, no compiling.

**How do I make subtitles (SRT) from a video for free, offline?**
`babelscribe video.mp4 -f srt` writes `video.srt` next to the video. Nothing is uploaded; it runs on your own computer.

**What is the most accurate free transcription for Thai?**
`babelscribe video.mp4 -l th --accurate` — Pathumma Whisper (NECTEC) for the text plus Whisper turbo for timing:
CER 8.9% on Google FLEURS vs 15.9% for plain Whisper turbo. Thonburian Whisper is available too (`--text-model thai-thonburian`).

**Can Claude / ChatGPT Codex / Gemini transcribe a video on my computer?**
Yes — add babelscribe as an MCP server (see [Use it from an AI app](../README.md#use-it-from-an-ai-app-mcp--no-terminal-needed)). Claude Desktop installs it with one click from
`babelscribe.mcpb`. The AI app can then find a file, transcribe it on your GPU, and proofread, translate or summarise the text.

**How fast is it?**
About 20x real time with Whisper large-v3-turbo on an AMD Radeon RX 9070 XT: a 19-minute talk in 48 seconds.

**Which languages are supported?**
All 99 Whisper languages, with automatic language detection. FLEURS error rates for 16 of them are in the [benchmark table](benchmarks.md#benchmark-16-languages-on-fleurs).

**Is it better than faster-whisper or WhisperX?**
Those are excellent on NVIDIA GPUs; on AMD / Intel GPUs they fall back to the CPU. babelscribe's niche is any GPU, zero setup,
and better Thai / Hindi through community fine-tunes. If you have an NVIDIA card and like Python, faster-whisper is a fine choice.

## Limitations (honest)
- Tested end to end so far on an AMD Radeon RX 9070 XT (Windows, Vulkan). CUDA, Linux and macOS builds are produced by CI; reports from those machines are welcome.
- Hybrid mode runs two models, so it is slower (≈1 min per minute of audio with a large fine-tune on that GPU).
- Proper nouns can still be misspelled — check names before publishing subtitles.

## Why babelscribe (vs. what already exists)
| | GPU on AMD / Intel | Windows, no build step | Video in, subtitles out | Long files don't loop | Better text for your language |
|---|---|---|---|---|---|
| **babelscribe** | ✅ Vulkan | ✅ prebuilt `whisper-cli` downloaded for you | ✅ ffmpeg bundled | ✅ `--max-context 0` by default | ✅ hybrid fine-tune text + turbo timing |
| whisper.cpp (raw) | ✅ Vulkan — if you compile it | ❌ official releases ship no Windows Vulkan build | ❌ WAV 16 kHz only | ⚠️ you must know the flag | ❌ |
| faster-whisper / WhisperX | ❌ GPU = NVIDIA CUDA only | ✅ pip | ✅ | ⚠️ | ⚠️ manual |
| Cloud APIs | n/a (cloud) | ✅ | ✅ | ✅ | ❌ — and your audio leaves your machine, paid per minute |

babelscribe does **not** replace those projects — it stands on whisper.cpp and simply removes the hard parts:
compiling for your GPU, converting media, picking the right device, avoiding the long-file repeat bug, and combining
a language-specific fine-tune with accurate timestamps.
