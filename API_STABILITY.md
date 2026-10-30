# API stability and deprecation policy

Applies from 1.0. Before 1.0 (0.x) minor versions may still change things, but we follow the same rules where we can.

## What is public

| Surface | Public | Not public |
|---|---|---|
| CLI | command names (`babelscribe FILE`, `devices`, `models`, `doctor`, `mcp`) and their flags | the exact wording of `--help` and log lines |
| Python | `babelscribe.api.transcribe_file` (and its keyword arguments and returned keys) | every other module (`backend`, `models`, `transcribe`, `hybrid`, `align`, `writers`, `doctor`) |
| MCP | tool names and their argument names/types: `transcribe`, `transcribe_folder`, `find_media`, `list_devices`, `list_languages_and_models` | tool descriptions, the text of the instructions |
| Files | `srt`, `vtt`, `txt`, `json` outputs (the `json` keys `meta` and `segments`) | model and binary cache layout under `~/.babelscribe` |

## Rules (semantic versioning)

- **Patch (1.0.x):** bug fixes only.
- **Minor (1.x.0):** may add flags, keyword arguments (always with a default), MCP arguments (always with a default), tools and JSON keys. Existing ones keep working.
- **Major (x.0.0):** may remove or rename public things.
- **Deprecation:** a public item is first marked deprecated for at least one minor release (CLI: a warning on stderr; Python: `DeprecationWarning`; MCP: noted in the argument description) and listed in the changelog. It is removed no earlier than the next major release.
- Positional order of `transcribe_file` arguments is not public: pass them by keyword.

## How it is enforced

`tests/test_api_stability.py` pins the public names above. Adding to them is fine; removing or renaming one fails the test, which is the cue to follow the deprecation steps first.
