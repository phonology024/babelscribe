# babelscribe plugin

Turn audio and video files on your computer into subtitles (SRT, VTT) and plain text in any of Whisper's 99 languages,
using your own graphics card — AMD Radeon, NVIDIA, Intel Arc or Apple Silicon — or the CPU. Everything runs locally.

## Use it
Ask Claude, for example: *"Make English subtitles for the newest video in my Downloads"*, *"Transcribe interview.mp3"*, or
*"ทำซับไทยให้คลิปล่าสุด แบบแม่นที่สุด"*. Claude finds the file, transcribes it on your GPU, writes `.srt` and `.txt` next to
it, and can then fix names, translate the subtitles or summarise them. Use accurate mode for the fewest errors; it is much
better for Thai and Hindi.

Requires [uv](https://docs.astral.sh/uv/) (the MCP server starts with `uvx babelscribe==0.3.2 mcp`). Works in Claude Code
and in Cowork sessions on your computer; claude.ai chat cannot start local servers.

## What it runs, downloads and sends
- **Runs:** the `babelscribe` Python package (MIT) from PyPI, pinned to 0.3.2, as a local MCP server over stdio. It runs
  ffmpeg (bundled via imageio-ffmpeg) and whisper.cpp's `whisper-cli` on your machine.
- **Downloads on first use:** `whisper-cli` for your OS/GPU from https://github.com/phonology024/babelscribe/releases,
  Whisper models from https://huggingface.co/ggerganov/whisper.cpp, and in accurate mode the Thai or Hindi fine-tune from
  its Hugging Face repository. Cached in `~/.babelscribe`.
- **Sends:** nothing. No telemetry or uploads. The transcript text is returned only to Claude, in your conversation.

## Tools
`transcribe` (writes subtitle/text files), `find_media` (lists media files in Downloads, Videos, Desktop, Music,
Documents), `list_devices`, `list_languages_and_models`.

## Privacy Policy
See https://phonology024.github.io/babelscribe/privacy.html — no data collection, no third-party sharing, local storage
only, contact via https://github.com/phonology024/babelscribe/issues.

## Licence
MIT. Built on whisper.cpp and OpenAI Whisper; fine-tunes belong to their authors.
