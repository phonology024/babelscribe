# Changelog

What changed in each release, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [semantic versioning](https://semver.org) as described in [API_STABILITY.md](API_STABILITY.md).
A change is written under **Unreleased** in the same pull request that makes it; `tools/release.py X.Y.Z` turns that
section into the release's section.

## [Unreleased]

### Added
- MCP tool `transcribe_folder`: every audio/video file in a folder in one request, one summary back; a file that
  fails does not stop the rest ([#36](https://github.com/phonology024/babelscribe/pull/36)).
- Docker image (CPU by default, Vulkan as a build argument), built and tested in CI and pushed to GHCR on a version
  tag ([#40](https://github.com/phonology024/babelscribe/pull/40)).
- The Claude Code plugin can be installed from this repository's own marketplace
  ([#44](https://github.com/phonology024/babelscribe/pull/44)).
- `PKGBUILD` for the Arch User Repository in `packaging/aur` (not yet submitted)
  ([#41](https://github.com/phonology024/babelscribe/pull/41)).
- `CHANGELOG.md`, `RELEASING.md`, `tools/release.py` (one-command version bump and packaging hashes), and PyPI
  trusted publishing from the version tag ([#54](https://github.com/phonology024/babelscribe/issues/54)).

### Fixed
- Linux arm64 and Intel macOS asked for a prebuilt `whisper-cli` that was never built and got a bare "HTTP Error 404".
  They now get the list of builds that exist and how to build one
  ([#39](https://github.com/phonology024/babelscribe/pull/39)).

### Documentation
- Speaker diarization: the options and their measured cost ([#45](https://github.com/phonology024/babelscribe/pull/45)).

## [0.4.0] - 2026-11-05

### Added
- `babelscribe doctor`: checks your setup and reports what is missing.
- `--prompt "names, terms"`: custom vocabulary (`vocabulary` in the MCP `transcribe` tool).
- `--translate`: translates speech to English (`translate` in MCP).
- `--max-line-chars`: subtitle line wrapping, with a smaller default for Thai and CJK.
- `-f ass`: karaoke subtitles that highlight each word as it is spoken.
- `vietnamese-toantam` for `--text-model`. It has no FLEURS benchmark yet, so `--accurate` does not use it.
- `API_STABILITY.md`, and a Scoop manifest in `packaging/scoop` (not yet submitted to a bucket).
- CI on Python 3.9 to 3.13 on Windows, Linux and macOS.

### Fixed
- Names with dots keep them, so `meeting.v1.mp4` and `meeting.v2.mp4` no longer overwrite each other's subtitles.
- `-o` creates its output folder before the slow work starts.
- An unknown or non-numeric `--device` fails straight away and lists the devices that exist.

### Changed
- `-o` is a base path and the extension is always appended: `-o x.srt` writes `x.srt.srt`. Use `-o x`.

## [0.3.2] - 2026-10-06

### Added
- MCP server (`babelscribe mcp`): transcribe from any AI app that supports local MCP servers.
- Claude Desktop extension (`babelscribe.mcpb`) and a Claude Code plugin.
- Listing in the MCP Registry, published from CI on each version tag.
- Privacy policy and a contributor guide.

### Fixed
- The device probe no longer passes `-np`, so static builds still list their GPUs.

## [0.2.1] - 2026-10-06

### Fixed
- Prebuilt x64 binaries are portable (AVX2 baseline) instead of built for the CI machine's CPU.
- A cached `whisper-cli` that crashes with "illegal instruction" is deleted and downloaded again.

## [0.2.0] - 2026-10-06

### Added
- `--accurate`: large-v3 with beam search, or the best fine-tune for the language.
- Benchmarks: 16 languages on FLEURS, and four TED / TEDx talks scored against human captions.

## [0.1.1] - 2026-10-06

### Changed
- Linux CUDA binaries are built in the NVIDIA container. Windows CUDA is dropped: the Vulkan build covers NVIDIA.
- A release publishes whichever binaries built, so one failing flavour does not block the others.

## [0.1.0] - 2026-10-06

### Added
- First release: any audio or video file to SRT / VTT / TXT / JSON in Whisper's 99 languages, on AMD, NVIDIA, Intel
  and Apple GPUs or the CPU, through prebuilt whisper.cpp binaries (Vulkan, CUDA, Metal).
- Hybrid mode: a language fine-tune for the text, `large-v3-turbo` for the timing.
