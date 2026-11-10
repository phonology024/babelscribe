# Homebrew formula

The formula is [`HomebrewFormula/babelscribe.rb`](../../HomebrewFormula/babelscribe.rb) at the repository root.
It lives there, not in this folder, because `brew tap` only looks in `Formula/`, `HomebrewFormula/` or the root
of a repository.

Homebrew core does not carry `anyio`, `mcp` or `imageio-ffmpeg` as formulae, so all 29 Python dependencies are
vendored as `resource` blocks, which is what `Language::Python::Virtualenv` expects. They are built from source,
which is why the formula needs `rust` and `pkgconf` at build time and `openssl@3`. `ffmpeg` is a normal
dependency: the `imageio-ffmpeg` sdist carries no ffmpeg binary, and babelscribe looks on `PATH` first.

## Install

```bash
brew tap phonology024/babelscribe https://github.com/phonology024/babelscribe
brew trust phonology024/babelscribe      # current Homebrew refuses formulae from a tap it has not been told to trust
brew install phonology024/babelscribe/babelscribe
```

The first install builds the Rust-based dependencies (`cryptography`, `pydantic-core`, `rpds-py`) and takes a
few minutes.

## After a release

The sdist only exists once the release is on PyPI, so this is a follow-up step:

```bash
# put the new url + sha256 in the formula (https://pypi.org/pypi/babelscribe/json, the sdist entry), then
brew update-python-resources phonology024/babelscribe/babelscribe   # only needed when dependencies changed
brew style phonology024/babelscribe/babelscribe                      # must report "no offenses detected"
```

`tests/test_homebrew_formula.py` fails when the formula's version is not the package's `__version__`.

## Verified

In the `homebrew/brew` container (Linux x86_64, Homebrew updated on 2026-11-10), with the formula in a local tap:

| Command | Result |
|---|---|
| `brew style` | no offenses detected |
| `brew install --build-from-source` | `babelscribe/0.4.0: 1,033 files, 23.4MB, built in 5 minutes` |
| `brew test` | passed |
| `brew audit --strict` | no problems reported |
| `babelscribe --version`, `babelscribe doctor` | `0.4.0`; Python 3.12 from the formula's venv; `FFmpeg: OK` |

**Not verified:** macOS. The same formula on a Mac uses the system libffi and Apple's toolchain, and nobody has
run it there yet. `brew update-python-resources` was not re-run for 0.4.0 (the dependency list did not change
from 0.3.2, and the install above used these exact resources). No transcription was run in the container.

## Note for homebrew-core

`brew audit --new-formula` wants a `test do` block that does more than `--version`. The current one is
deliberately cheap: a real transcription in `brew test` would download a model.
