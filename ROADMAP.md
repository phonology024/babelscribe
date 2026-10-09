# babelscribe roadmap

Releases, what goes in each, and where help is wanted. Dates are targets, not promises. Last updated 2026-10-10.
Everything below is a GitHub issue; each release is a [milestone](https://github.com/phonology024/babelscribe/milestones).

## Where we are
- **PyPI: 0.3.2** (2026-10-06). Any audio/video → SRT / VTT / TXT / JSON, 99 languages, on AMD / NVIDIA / Intel / Apple GPU or CPU.
- MCP server (`uvx babelscribe mcp`), one-click Claude Desktop extension, Claude Code plugin, MCP Registry listing.
- **1,114 downloads** on [mcprush.com](https://mcprush.com) — thank you.

## Releases
| PyPI version | Target | Theme | Contents |
|---|---|---|---|
| **0.4.0** | 2026-10-20 | Smart & measured | `--smart` (fast pass, redo only low-confidence parts) and `--draft`; VAD on by default; progress bar and real MCP progress ([#6](https://github.com/phonology024/babelscribe/issues/6)); transcribe.cpp text models (Qwen3-ASR, Cohere); `babelscribe bench` hardware report |
| **0.4.1** | 2026-11-03 | Subtitle polish | Max characters per line, two-line cues ([#4](https://github.com/phonology024/babelscribe/issues/4)); first verified NVIDIA / Intel / Linux / macOS results ([#3](https://github.com/phonology024/babelscribe/issues/3)) |
| **0.5.0** | 2026-11-30 | MCP power | Whole-folder batch ([#7](https://github.com/phonology024/babelscribe/issues/7)); `--translate` ([#8](https://github.com/phonology024/babelscribe/issues/8)); `babelscribe doctor` ([#10](https://github.com/phonology024/babelscribe/issues/10)); `--prompt` custom vocabulary ([#11](https://github.com/phonology024/babelscribe/issues/11)); Docker image ([#12](https://github.com/phonology024/babelscribe/issues/12)) |
| **0.6.0** | 2027-01-15 | More languages | Arabic ([#2](https://github.com/phonology024/babelscribe/issues/2)), Vietnamese ([#1](https://github.com/phonology024/babelscribe/issues/1)), Korean ([#13](https://github.com/phonology024/babelscribe/issues/13)), Indonesian ([#14](https://github.com/phonology024/babelscribe/issues/14)), Turkish ([#15](https://github.com/phonology024/babelscribe/issues/15)); FLEURS table for the new text models ([#16](https://github.com/phonology024/babelscribe/issues/16)) |
| **0.7.0** | 2027-03-15 | Subtitle craft | Speaker-label study ([#9](https://github.com/phonology024/babelscribe/issues/9)); karaoke / ASS output ([#17](https://github.com/phonology024/babelscribe/issues/17)); simple drag-and-drop app ([#18](https://github.com/phonology024/babelscribe/issues/18)) |
| **1.0.0** | 2027-05-31 | Stable | API and MCP schema stability policy ([#19](https://github.com/phonology024/babelscribe/issues/19)); CI on Windows / Linux / macOS × Python 3.9–3.13 ([#20](https://github.com/phonology024/babelscribe/issues/20)); "verified" claims backed by hardware reports |

Patch releases (0.x.y) ship fixes as they come. Minor versions may change flags; from 1.0 on, breaking changes need a major version.

## Need help? (open for anyone)
Comment on an issue to claim it. Items marked ★ are small and good first PRs.

| What | Issues |
|---|---|
| **Test on your hardware** — run `babelscribe bench` (0.4.0+) or `babelscribe devices`, paste the result | [#3](https://github.com/phonology024/babelscribe/issues/3) ★ |
| **Language fine-tunes** — find one, measure on FLEURS, open a PR (even "it lost" is useful) | [#1](https://github.com/phonology024/babelscribe/issues/1) ★ [#2](https://github.com/phonology024/babelscribe/issues/2) ★ [#13](https://github.com/phonology024/babelscribe/issues/13) ★ [#14](https://github.com/phonology024/babelscribe/issues/14) ★ [#15](https://github.com/phonology024/babelscribe/issues/15) ★ [#16](https://github.com/phonology024/babelscribe/issues/16) |
| **Small features** | [#4](https://github.com/phonology024/babelscribe/issues/4) ★ [#8](https://github.com/phonology024/babelscribe/issues/8) ★ [#10](https://github.com/phonology024/babelscribe/issues/10) ★ [#11](https://github.com/phonology024/babelscribe/issues/11) ★ |
| **Packaging** — winget, Scoop, Homebrew, conda-forge, AUR, Docker | [#21](https://github.com/phonology024/babelscribe/issues/21) ★ [#22](https://github.com/phonology024/babelscribe/issues/22) [#23](https://github.com/phonology024/babelscribe/issues/23) ★ [#12](https://github.com/phonology024/babelscribe/issues/12) |
| **Translations** of README / guides | [#24](https://github.com/phonology024/babelscribe/issues/24) ★ |
| **Directory submissions** (Smithery, Glama, PulseMCP, …) | [#25](https://github.com/phonology024/babelscribe/issues/25) ★ |
| **Showcase** — share your before/after | [#26](https://github.com/phonology024/babelscribe/issues/26) ★ |
| **Benchmarks on noisy / long audio** | [#27](https://github.com/phonology024/babelscribe/issues/27) |
| **Bigger projects** — GUI, ASS output, CI matrix, speaker labels | [#18](https://github.com/phonology024/babelscribe/issues/18) [#17](https://github.com/phonology024/babelscribe/issues/17) [#20](https://github.com/phonology024/babelscribe/issues/20) [#9](https://github.com/phonology024/babelscribe/issues/9) |

Filter on GitHub: [`need help`](https://github.com/phonology024/babelscribe/labels/need%20help) ·
[`good first issue`](https://github.com/phonology024/babelscribe/labels/good%20first%20issue). Setup and recipes: [CONTRIBUTING.md](CONTRIBUTING.md).
