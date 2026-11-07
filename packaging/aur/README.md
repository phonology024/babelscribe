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
| `python-build`, `python-installer`, `python-wheel`, `python-setuptools` | build time only |
| `ffmpeg` (optdepends) | decoding; without it, set `BABELSCRIBE_*` to a whisper.cpp build and let it use a system ffmpeg |
| `python-imageio-ffmpeg` (optdepends) | the bundled ffmpeg the Python package normally uses — **only in the AUR**, which is why it is not a hard dependency |
| `python-pythainlp` (optdepends) | Thai word boundaries in hybrid mode |

`python-imageio-ffmpeg` is the one dependency that is not in an official Arch repo. Making it a hard
dependency would force this PKGBUILD into the AUR as `babelscribe` with an AUR-only dep, which is allowed but
slows down every install for a feature most users do not need. `ffmpeg` from `extra` covers the common case.

## Updating for a new release

1. Bump `pkgver` (and reset `pkgrel` to 1).
2. Put the new `https://pypi.org/pypi/babelscribe/json` sdist `sha256` into `sha256sums`.
3. Regenerate `.SRCINFO`:

   ```bash
   makepkg --printsrcinfo > .SRCINFO
   ```

CI keeps this honest: `tests/test_aur_pkgbuild.py` fails when `pkgver` or the checksum drifts from what PyPI
says the current release is.

## Verified

Built and installed on `archlinux:latest` (as a `linux/amd64` container on an Apple Silicon host), then run
end to end: `makepkg` produced `babelscribe-0.3.2-1-any.pkg.tar.zst`, `pacman -U` installed it, and
`babelscribe tone.wav -m tiny -f srt,txt` downloaded whisper-cli and the model and wrote valid subtitles.
Note that the container build proves the PKGBUILD is correct, not that it has been tested on a physical Arch
install with a GPU.
