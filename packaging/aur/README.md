# AUR package (Arch Linux)

`packaging/aur/PKGBUILD` installs babelscribe from the PyPI source tarball. It is intended for
[babelscribe on the AUR](https://aur.archlinux.org/packages?K=babelscribe), not for the Arch repos.

## Building and installing

```bash
cd packaging/aur
makepkg -si                    # builds, then installs with pacman
```

## What it does and does not pull in

| Package | Why |
|---|---|
| `python`, `python-anyio`, `python-mcp` | runtime imports; all three are in the `extra` repo |
| `ffmpeg` | decoding every input file; in `extra`. A hard dependency, so a default install can transcribe |
| `python-build`, `python-installer`, `python-wheel`, `python-setuptools` | build time only |
| `python-pythainlp` (optdepends) | Thai word boundaries in hybrid mode |

On PyPI the package depends on `imageio-ffmpeg`, which bundles an ffmpeg binary. That package is only in the
AUR, and babelscribe looks for `ffmpeg` on `PATH` first anyway, so this PKGBUILD depends on Arch's own `ffmpeg`
instead and does not need `python-imageio-ffmpeg` at all.

## Updating for a new release

1. Bump `pkgver` (and reset `pkgrel` to 1).
2. Put the new `https://pypi.org/pypi/babelscribe/json` sdist `sha256` into `sha256sums`.
3. Regenerate `.SRCINFO`:

   ```bash
   makepkg --printsrcinfo > .SRCINFO
   ```

**Every version bump has to touch this folder**, because `tests/test_aur_pkgbuild.py` fails when `pkgver` is
not the package's `__version__`. The sdist only exists after the release is on PyPI, so the order is: release,
then update `pkgver` + `sha256sums` + `.SRCINFO` here.

What the tests check: `pkgver` equals `__version__`, `.SRCINFO` agrees with `PKGBUILD`, the checksum is a real
64-hex digest, and, when PyPI is reachable, that the digest is the one PyPI publishes for that sdist. Without
network that last test is skipped, so an offline run does not prove the checksum.

## Verified

Built and installed in an `archlinux:latest` container (linux/amd64) on 2026-11-10, then run end to end:
`makepkg -s` produced `babelscribe-0.4.0-1-any.pkg.tar.zst`, `pacman -U` installed it together with `ffmpeg`,
`python-anyio` and `python-mcp` from `extra`, and `babelscribe talk.wav -m tiny -l en -f srt --flavor cpu`
downloaded whisper-cli and the model and wrote correct subtitles for a spoken sentence. `.SRCINFO` is byte for
byte what `makepkg --printsrcinfo` printed there.

A container build proves the PKGBUILD is correct. It does not prove a physical Arch install with a GPU works:
the container has none, so only the CPU build ran.
