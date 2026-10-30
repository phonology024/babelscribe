# Homebrew formula

`packaging/homebrew/babelscribe.rb` is the formula, kept here so it is versioned with the release it packages.
Homebrew core does not carry `python-anyio`, `python-mcp` or `python-imageio-ffmpeg`, so the formula vendors
all 29 Python dependencies as `resource` blocks, which is what `Language::Python::Virtualenv` expects.

## Install from this file (no tap needed)

```bash
brew install --build-from-source packaging/homebrew/babelscribe.rb
```

For a permanent install, put the file in a tap:

```bash
brew tap phonology024/babelscribe https://github.com/phonology024/babelscribe
brew install phonology024/babelscribe/babelscribe
```

## Regenerating the resource blocks after a release

Do not hand-edit them. `brew update-python-resources` resolves the dependency tree and writes the `url`/`sha256`
for every package:

```bash
# put the new version + sha256 in the formula first, then
brew update-python-resources packaging/homebrew/babelscribe.rb
brew style packaging/homebrew/babelscribe.rb    # must report "no offenses detected"
```

Get the `sha256` from `https://pypi.org/pypi/babelscribe/json` (`urls[].digests.sha256` for the sdist).

## Verified

- `brew style` — no offenses.
- `brew update-python-resources` resolved all 29 dependencies from PyPI and generated the blocks.
- The resulting dependency set installs and runs: a virtualenv on Homebrew's `python@3.12` with
  `pip install babelscribe==0.3.2` yields a working `babelscribe --version` → `0.3.2`.

**Not verified:** `brew install` and `brew audit` themselves. Both refuse to run on the machine this was
prepared on (`Your Command Line Tools are too outdated` — CLT 16.4 vs the Xcode 27 that Homebrew 7 wants),
which is a property of that host, not of the formula. Run both on a current macOS before submitting upstream.

## Note for homebrew-core

If this ever goes to homebrew-core, `brew audit --new-formula` also wants a `test do` block that exercises
more than `--version`; the current one only checks the binary starts. That is deliberate: a real transcription
in the test block would download a 1.6 GB model during `brew test`.
