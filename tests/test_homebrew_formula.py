"""Keeps packaging/homebrew/babelscribe.rb in step with the release and with PyPI.

A Homebrew formula pins two things that go stale silently: the sdist sha256 and the vendored Python
dependencies. A wrong sha256 fails at `brew install`; a missing resource fails at import time. Both are
caught here without network access.
"""
import re
from pathlib import Path

import pytest

FORMULA = Path(__file__).resolve().parent.parent / "packaging" / "homebrew" / "babelscribe.rb"


@pytest.fixture(scope="module")
def formula() -> str:
    if not FORMULA.is_file():
        pytest.skip(f"{FORMULA} is not part of this checkout")
    return FORMULA.read_text(encoding="utf-8")


def test_class_and_install_method(formula):
    assert re.search(r"^class Babelscribe < Formula$", formula, re.MULTILINE)
    assert "Language::Python::Virtualenv" in formula
    assert "virtualenv_install_with_resources" in formula


def test_url_and_sha256_point_at_the_pypi_sdist(formula):
    from babelscribe import __version__
    url = re.search(r'^\s*url "([^"]+)"', formula, re.MULTILINE).group(1)
    sha = re.search(r'^\s*sha256 "([0-9a-f]{64})"', formula, re.MULTILINE).group(1)
    assert f"babelscribe-{__version__}.tar.gz" in url, f"url does not match version {__version__}"
    assert re.fullmatch(r"[0-9a-f]{64}", sha)


def test_license_present(formula):
    assert re.search(r'^\s*license "MIT"$', formula, re.MULTILINE)


def test_every_resource_has_url_and_sha(formula):
    blocks = re.findall(r'resource "([^"]+)" do\n(.*?)\n  end', formula, re.DOTALL)
    assert len(blocks) >= 20, f"only {len(blocks)} resources: dependency vendoring looks broken"
    for name, body in blocks:
        assert re.search(r'url "https://files\.pythonhosted\.org/', body), f"{name}: not a PyPI url"
        assert re.search(r'sha256 "[0-9a-f]{64}"', body), f"{name}: missing or malformed sha256"


def test_runtime_dependencies_are_vendored(formula):
    """babelscribe imports these at runtime; a formula missing one fails at first run, not at install."""
    names = set(re.findall(r'resource "([^"]+)" do', formula))
    assert {"anyio", "mcp", "imageio-ffmpeg"} <= names


def test_test_block_does_not_download_a_model(formula):
    """A real transcription in `brew test` would pull ~1.6 GB; keep the smoke test cheap."""
    block = re.search(r"test do\n(.*?)\n  end", formula, re.DOTALL)
    assert block, "formula has no test block"
    assert "transcribe" not in block.group(1).lower()
