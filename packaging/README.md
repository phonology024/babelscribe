# Windows packaging

## Scoop — ready to submit

`scoop/babelscribe.json` installs babelscribe from the PyPI wheel into its own venv and shims both console scripts
(`babelscribe` and `babelscribe-mcp`). It follows the same pattern the official Main bucket uses for pip-installed
tools such as `git-machete`.

Validated against Scoop's own schema (`tests/data/scoop-schema.json`), and
`tests/test_windows_packaging.py` checks that the hash matches the wheel it points at and that the shims exist as
console scripts in `pyproject.toml`.

**To submit**, open a PR adding the file to a bucket. Two options:

- **`ScoopInstaller/Extras`** — the usual home for tools like this. The bucket has pip-based manifests already
  (`cookiecutter`, `cruft`), so the pattern is accepted.
- **A babelscribe bucket** — `scoop bucket add babelscribe https://github.com/phonology024/scoop-bucket` then
  `scoop install babelscribe/babelscribe`. Necessary if the Extras PR is declined; self-hosted buckets work fine.

Nothing in the repo needs to change for either route.

## winget — why it could not be done from the PyPI package

The issue asks for `winget install babelscribe`. That is not expressible today, for a structural reason rather than a
lack of effort.

**winget's manifest has no script installer type.** The `InstallerType` enum is:

```
msix, msi, appx, exe, zip, inno, nullsoft, wix, burn, pwa, portable
```

Every one of those needs a *binary artifact* — an MSI, an EXE, or a zip of executables. babelscribe is a pure-Python
package: the PyPI wheel is 27 KB of `.py` files with no executable in it, because `babelscribe.exe` only comes into
being when pip generates console-script shims for the interpreter it is installed into.

Three ways this is normally handled, and why none fit here:

1. **Ship a bundled EXE** (PyInstaller, Nuitka). This produces a ~40–80 MB single-file executable per architecture, has
   to be rebuilt and signed on every release, and duplicates the `pip install` path. It is a new release pipeline, not
   a manifest.
2. **Point at an EXE someone else ships.** babelscribe has no standalone Windows binary — it downloads
   `whisper-cli` at first run, but the Python CLI itself is the thing being installed.
3. **Use an existing winget `zip` installer with the Python embeddable runtime** pre-baked. This means committing a
   build artifact to the repo or to a release on every version bump.

This was checked rather than assumed: a code search of `microsoft/winget-pkgs` for `pip install` and
`files.pythonhosted.org` returns **zero** manifests, and known pip tools (`pipx`, `poetry`) are not present.

## Standalone build (no Python) — built by CI, which also unblocks winget

`standalone/` holds the recipe for `babelscribe-<version>-windows-x64.zip`: `babelscribe.exe` and
`babelscribe-mcp.exe` in one folder with Python and every library inside (PyInstaller, one-folder mode).
`.github/workflows/build-standalone.yml` builds it, tests it, and attaches it to the GitHub release when a version tag
is pushed.

| Measured on Windows 11 | |
|---|---|
| Folder size | 146 MB, of which 101 MB is ffmpeg (the same ffmpeg the pip install brings) |
| `babelscribe.exe --version` | 0.15 to 0.25 s |
| First run with an empty cache (downloads whisper-cli and the tiny model, transcribes an 11 s clip) | 5 s |

One-folder was chosen over one-file because a one-file executable unpacks all 146 MB to a temp folder on every start.
The python.org embeddable runtime plus wheels would be about the same size (ffmpeg dominates) and needs its own
launcher executables, so it was not pursued.

`standalone/smoke_test.py` is the test CI runs: it starts both programs with an environment that has no Python (no
`PATH` entry, no `PYTHON*` variables) and an empty babelscribe home, then checks `--version`, a real first-run
transcription, and an MCP handshake plus tool list over stdio.

Not included, on purpose:
- **Code signing.** The executables are unsigned, so SmartScreen shows "unknown publisher" the first time. A
  certificate costs money every year; that is the maintainer's decision.
- **The fine-tune converter** (`--text-model`, and `--accurate` for Thai / Hindi): it needs torch and transformers
  (about 2.5 GB). In the standalone build those options stop with the usual "needs extras" message; use the pip
  install for them.

**winget, once a release carries the zip.** winget can install a zip of portable executables, so the manifest
becomes a few lines per release (`wingetcreate new <zip url>` writes it and opens the PR against
`microsoft/winget-pkgs`):

```yaml
InstallerType: zip
NestedInstallerType: portable
NestedInstallerFiles:
  - RelativeFilePath: babelscribe\babelscribe.exe
    PortableCommandAlias: babelscribe
  - RelativeFilePath: babelscribe\babelscribe-mcp.exe
    PortableCommandAlias: babelscribe-mcp
Installers:
  - Architecture: x64
    InstallerUrl: https://github.com/phonology024/babelscribe/releases/download/v<version>/babelscribe-<version>-windows-x64.zip
    InstallerSha256: <from the .sha256 file next to the zip>
```

The Scoop manifest can then point at the same zip and drop its Python dependency.

## Testing note

The Scoop manifest was written on a machine with no Windows. What *was* verified:

- Scoop manifest valid against the official schema ✅
- Sha256 matches the live PyPI wheel ✅
- Shims match the console scripts in `pyproject.toml` ✅
- Autoupdate URL pattern resolves (HTTP 200) ✅

What is **not** verified: an actual `scoop install` on Windows. Someone on Windows 11 should run it before the bucket
PR is opened.