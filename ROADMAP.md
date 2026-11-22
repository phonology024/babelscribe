# babelscribe roadmap

Releases, what goes in each, and where help is wanted. Dates are targets, not promises. Last updated 2026-11-22.
Everything below is a GitHub issue; each release is a [milestone](https://github.com/phonology024/babelscribe/milestones).

## Where we are
- **PyPI: 0.5.0** (2026-11-22). Any audio/video → SRT / VTT / TXT / JSON / karaoke ASS in 99 languages, or the video with the subtitles burned in; translation into any language through your own local LLM. On AMD / NVIDIA / Intel / Apple GPU or CPU.
- MCP server (`uvx babelscribe mcp`), one-click Claude Desktop extension, Claude Code plugin with its own marketplace, MCP Registry listing.
- **1,114 downloads** on [mcprush.com](https://mcprush.com) — thank you.

## Releases
| PyPI version | Target | Theme | Contents |
|---|---|---|---|
| **0.4.0** | released 2026-11-05 | Everyday features | `babelscribe doctor` ([#10](https://github.com/phonology024/babelscribe/issues/10)); `--prompt` custom vocabulary ([#11](https://github.com/phonology024/babelscribe/issues/11)); subtitle line wrapping ([#4](https://github.com/phonology024/babelscribe/issues/4)); `--translate` ([#8](https://github.com/phonology024/babelscribe/issues/8)); karaoke / ASS output ([#17](https://github.com/phonology024/babelscribe/issues/17)); Vietnamese fine-tune option; `--device` and `-o` fixes |
| **0.5.0** | released 2026-11-22 | Batches and finished videos | Several files or a whole folder on the command line ([#52](https://github.com/phonology024/babelscribe/issues/52)); real % progress in MCP and a CLI progress bar ([#6](https://github.com/phonology024/babelscribe/issues/6)); MCP whole-folder batch ([#7](https://github.com/phonology024/babelscribe/issues/7)); `babelscribe convert`: re-wrap or re-export from the saved JSON, with reading-speed rules ([#57](https://github.com/phonology024/babelscribe/issues/57)); burn subtitles into the video (`--burn`, karaoke and shorts looks) ([#58](https://github.com/phonology024/babelscribe/issues/58)); translate subtitles into any language through a local LLM (`--translate-to`) ([#49](https://github.com/phonology024/babelscribe/issues/49)); checksum-verified, pinned whisper-cli downloads ([#53](https://github.com/phonology024/babelscribe/issues/53)); a real transcription in CI on every OS ([#55](https://github.com/phonology024/babelscribe/issues/55)); one-command releases and a changelog ([#54](https://github.com/phonology024/babelscribe/issues/54)); standalone Windows build, no Python needed ([#59](https://github.com/phonology024/babelscribe/issues/59)); Docker image on GHCR ([#12](https://github.com/phonology024/babelscribe/issues/12)); Homebrew formula and AUR PKGBUILD ([#22](https://github.com/phonology024/babelscribe/issues/22)), ([#23](https://github.com/phonology024/babelscribe/issues/23)) |
| **0.6.0** | 2027-01-15 | Faster, more languages | `--smart` (fast pass, redo only low-confidence parts) and `--draft`; VAD on by default; `babelscribe bench` hardware report; transcribe.cpp text models, Qwen3-ASR and Cohere ([#16](https://github.com/phonology024/babelscribe/issues/16)); smaller quantised fine-tunes if they hold accuracy ([#50](https://github.com/phonology024/babelscribe/issues/50)); Arabic ([#2](https://github.com/phonology024/babelscribe/issues/2)), Vietnamese ([#1](https://github.com/phonology024/babelscribe/issues/1)), Korean ([#13](https://github.com/phonology024/babelscribe/issues/13)), Indonesian ([#14](https://github.com/phonology024/babelscribe/issues/14)), Turkish ([#15](https://github.com/phonology024/babelscribe/issues/15)); prebuilt binaries for linux-arm64 and Intel macOS ([#56](https://github.com/phonology024/babelscribe/issues/56)); NVIDIA / Intel / Linux hardware reports ([#3](https://github.com/phonology024/babelscribe/issues/3)) |
| **0.7.0** | 2027-03-15 | Easier for everyone | Speaker labels ([#51](https://github.com/phonology024/babelscribe/issues/51)); winget ([#21](https://github.com/phonology024/babelscribe/issues/21)); simple drag-and-drop app ([#18](https://github.com/phonology024/babelscribe/issues/18)) |
| **1.0.0** | 2027-05-31 | Stable | API and MCP schema stability policy in force ([API_STABILITY.md](API_STABILITY.md)); every "works on" claim backed by a hardware report ([#3](https://github.com/phonology024/babelscribe/issues/3)); noisy and long-recording benchmark, not only clean read speech ([#27](https://github.com/phonology024/babelscribe/issues/27)) |

Patch releases (0.x.y) ship fixes as they come. Minor versions may change flags; from 1.0 on, breaking changes need a major version.

## Need help? (open for anyone)
Comment on an issue to claim it. Items marked ★ are small and good first PRs.

| What | Issues |
|---|---|
| **Test on your hardware** — run `babelscribe doctor` and `babelscribe devices`, transcribe one file, paste the result. NVIDIA, Intel Arc and Linux are still unreported | [#3](https://github.com/phonology024/babelscribe/issues/3) ★ |
| **Language fine-tunes** — find one, measure on FLEURS, open a PR (even "it lost" is useful) | [#1](https://github.com/phonology024/babelscribe/issues/1) ★ [#2](https://github.com/phonology024/babelscribe/issues/2) ★ [#13](https://github.com/phonology024/babelscribe/issues/13) ★ [#14](https://github.com/phonology024/babelscribe/issues/14) ★ [#15](https://github.com/phonology024/babelscribe/issues/15) ★ [#16](https://github.com/phonology024/babelscribe/issues/16) [#50](https://github.com/phonology024/babelscribe/issues/50) |
| **Small features** | [#50](https://github.com/phonology024/babelscribe/issues/50) [#56](https://github.com/phonology024/babelscribe/issues/56) |
| **Packaging** — Scoop, Homebrew, conda-forge, Docker on a GPU, ARM builds | [#21](https://github.com/phonology024/babelscribe/issues/21) ★ [#22](https://github.com/phonology024/babelscribe/issues/22) [#12](https://github.com/phonology024/babelscribe/issues/12) [#56](https://github.com/phonology024/babelscribe/issues/56) |
| **Translations** of README / guides, any language Whisper supports | [#24](https://github.com/phonology024/babelscribe/issues/24) ★ |
| **Directory submissions** (Smithery, mcp.so, …) | [#25](https://github.com/phonology024/babelscribe/issues/25) ★ |
| **Showcase** — share your before/after | [#26](https://github.com/phonology024/babelscribe/issues/26) ★ |
| **Benchmarks on noisy / long audio**, and one real multi-speaker recording for speaker labels | [#27](https://github.com/phonology024/babelscribe/issues/27) [#51](https://github.com/phonology024/babelscribe/issues/51) |
| **Bigger projects** — desktop app, speaker labels | [#18](https://github.com/phonology024/babelscribe/issues/18) [#51](https://github.com/phonology024/babelscribe/issues/51) |

Filter on GitHub: [`help wanted`](https://github.com/phonology024/babelscribe/labels/help%20wanted) ·
[`good first issue`](https://github.com/phonology024/babelscribe/labels/good%20first%20issue). Setup and recipes: [CONTRIBUTING.md](CONTRIBUTING.md).
