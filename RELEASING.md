# Releasing babelscribe

A release is: run one command, merge one PR, push one tag, merge one follow-up PR. Only the maintainer does steps 3
and later.

| # | Step | Who / what does it |
|---|---|---|
| 1 | `python tools/release.py X.Y.Z` | you; edits files only |
| 2 | Release PR: review, CI green, merge | you |
| 3 | `git tag vX.Y.Z && git push origin vX.Y.Z` on the merge commit | you |
| 4 | PyPI upload | `publish.yml`, job `pypi` (trusted publishing) |
| 5 | MCP Registry | `publish.yml`, job `registry`, after the version is visible on PyPI |
| 6 | Binaries + `.mcpb` + `SHA256SUMS` on the GitHub release; Docker image on GHCR | `build-binaries.yml`, `docker.yml` |
| 7 | `python tools/release.py --after-pypi`, packaging PR, merge | you |

## 1. Bump

```bash
python tools/release.py --check      # every pinned place matches the current version? start from a clean state
python tools/release.py X.Y.Z
```

This writes the new version into every file that pins it (`pyproject.toml`, `babelscribe/__init__.py`, `server.json`,
the `.mcpb` and plugin manifests, `docs/index.html`, the Scoop / AUR / Homebrew files, the "PyPI:" line of the
roadmap) and turns the **Unreleased** section of `CHANGELOG.md` into the release's section. It stops if that
section is empty.

By hand, in the same PR:
- the release row in the `ROADMAP.md` table (and the same row in `docs/llms-full.txt`);
- read the new `CHANGELOG.md` section once as a user would.

The Scoop, AUR and Homebrew files now name the new version with the **old** hashes. That is expected: the files
they hash do not exist until step 4. Nobody installs from them before step 7.

## 2. Release PR

`pytest` must pass: the tests compare every pinned version with `babelscribe.__version__`, and
`tests/test_release_tool.py` fails if a file pins the version and the tool does not know it. Merge.

## 3. Tag

Tag the merge commit `vX.Y.Z` and push the tag. The tag starts three workflows. They do not depend on each
other except where the table says so:

- `publish.yml`: builds the sdist and wheel, uploads them to PyPI, then waits until PyPI serves that version and
  publishes `server.json` to the MCP Registry. If the PyPI job fails, upload by hand (`python -m build && twine
  upload dist/*`) and re-run the `registry` job: it only needs the version to be on PyPI, however it got there.
- `build-binaries.yml`: builds `whisper-cli` for each platform, transcribes a real file with each build, and
  attaches the zips, `babelscribe.mcpb` and `SHA256SUMS` to the GitHub release.
- `docker.yml`: builds the image from the tagged source (not from PyPI) and pushes it to GHCR.

The package does not download the binaries of its own tag. It downloads the release named by `BINARY_TAG` in
`babelscribe/backend.py` and checks the sha256 listed there. To move to newer binaries, change `BINARY_TAG` and
copy the digests from that release's `SHA256SUMS` in a normal PR, any time after step 6.

## 4–6. Check

- https://pypi.org/project/babelscribe/ shows X.Y.Z; `pip install -U babelscribe && babelscribe --version`.
- The GitHub release has six `whisper-cli-*.zip`, `babelscribe.mcpb` and `SHA256SUMS`. Write the release text from
  the `CHANGELOG.md` section.
- `docker run --rm ghcr.io/phonology024/babelscribe:X.Y.Z --version`.

## 7. Packaging hashes

```bash
python tools/release.py --after-pypi
```

Reads the sdist and wheel digests of the current version from PyPI and writes them into
`packaging/scoop/babelscribe.json`, `packaging/aur/PKGBUILD`, `packaging/aur/.SRCINFO` and
`HomebrewFormula/babelscribe.rb`. Open a PR with that diff and merge it. If the dependency list changed in this
release, also run `brew update-python-resources` (see `packaging/homebrew/README.md`).

## One-time setup: PyPI trusted publishing

On https://pypi.org/manage/project/babelscribe/settings/publishing/ add a GitHub publisher: owner `phonology024`,
repository `babelscribe`, workflow `publish.yml`, environment `pypi`. No token is stored anywhere. Until this is
done the `pypi` job fails and the manual upload in step 3 applies.
