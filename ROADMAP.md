# babelscribe roadmap

Where babelscribe is going next. It's a plan, not a promise — priorities follow what people actually ask for in
[issues](https://github.com/phonology024/babelscribe/issues). Last updated 2026-10-10.

## Where we are
- Transcribes any audio/video to SRT / VTT / TXT / JSON in 99 languages on AMD, NVIDIA, Intel, Apple GPUs or CPU (whisper.cpp).
- MCP server (`uvx babelscribe mcp`) and a one-click Claude Desktop extension (`.mcpb`); Claude Code plugin.
- Listed on the MCP Registry; **1,114 downloads** on [mcprush.com](https://mcprush.com) so far — thank you.
- Hybrid mode (community fine-tune text + turbo timing) for Thai and Hindi; 16-language FLEURS benchmark.

## Next — after 13 Oct 2026
Tracked in [#5](https://github.com/phonology024/babelscribe/issues/5). Starter-friendly items are labelled `good first issue`.

| Theme | Item | Issue |
|---|---|---|
| Subtitles | Max characters per line, two-line cues | [#4](https://github.com/phonology024/babelscribe/issues/4) |
| Hardware | Verified reports for NVIDIA, Intel Arc, Linux, macOS | [#3](https://github.com/phonology024/babelscribe/issues/3) |
| Accuracy | Arabic and Vietnamese fine-tunes that beat large-v3 | [#2](https://github.com/phonology024/babelscribe/issues/2), [#1](https://github.com/phonology024/babelscribe/issues/1) |
| MCP | Progress updates for long files, so AI apps don't time out | #6 |
| MCP | Transcribe a whole folder in one request | #7 |
| Features | Translate to English (`--translate`) | #8 |
| Features | Speaker labels — feasibility study | #9 |

## Later (ideas, not scheduled)
- More language fine-tunes (Korean, Indonesian, Turkish…) — see [CONTRIBUTING.md](CONTRIBUTING.md).
- Publish to more MCP directories and AI-app plugin marketplaces.
- Published benchmarks on NVIDIA / Intel / Apple hardware once reports arrive.

## How to help
Run `babelscribe devices`, transcribe a file, and file a *Hardware report*; or add a fine-tune for your language
(about five lines). Details in [CONTRIBUTING.md](CONTRIBUTING.md).
