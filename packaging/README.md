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

## winget — cannot be done for this package, and here is why

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

**If a Windows standalone build is ever wanted**, the smallest path is a PyInstaller one-file build per architecture
attached to the GitHub release, and then a `zip`/`portable` manifest pointing at it. That is a real feature with real
maintenance cost, so it belongs in its own issue rather than in the packaging one.

## Testing note

Neither manifest can be exercised on this machine: there is no Windows and no PowerShell here. What *was* verified:

- Scoop manifest valid against the official schema ✅
- Sha256 matches the live PyPI wheel ✅
- Shims match the console scripts in `pyproject.toml` ✅
- Autoupdate URL pattern resolves (HTTP 200) ✅

What is **not** verified: an actual `scoop install` on Windows. Someone on Windows 11 should run it before the bucket
PR is opened.