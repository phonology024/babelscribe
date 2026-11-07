"""Keeps packaging/aur/PKGBUILD in step with the release it is supposed to package.

A stale pkgver or checksum in an AUR package is the classic packaging bug: the PKGBUILD looks fine, and every
user gets "ERROR: One or more files did not pass the validity check" until someone notices. This checks the
fields that must match the current version in pyproject.toml, without needing network access.
"""
import re
from pathlib import Path

import pytest

PKGBUILD = Path(__file__).resolve().parent.parent / "packaging" / "aur" / "PKGBUILD"


@pytest.fixture(scope="module")
def pkgbuild() -> str:
    if not PKGBUILD.is_file():
        pytest.skip(f"{PKGBUILD} is not part of this checkout")
    return PKGBUILD.read_text(encoding="utf-8")


def test_pkgver_matches_the_package_version(pkgbuild):
    from babelscribe import __version__
    ver = re.search(r"^pkgver=(\S+)$", pkgbuild, re.MULTILINE)
    assert ver, "PKGBUILD has no pkgver"
    assert ver.group(1) == __version__, "bump pkgver when the package version changes"


def test_checksum_is_a_real_sha256_not_skip(pkgbuild):
    sums = re.search(r"^sha256sums=\((.*?)\)$", pkgbuild, re.MULTILINE | re.DOTALL)
    assert sums, "PKGBUILD has no sha256sums"
    digest = sums.group(1).strip().strip("'\"")
    assert re.fullmatch(r"[0-9a-f]{64}", digest), (
        f"sha256sums is {digest!r}: AUR rejects SKIP for source tarballs, so a real digest is required")


def test_source_url_points_at_the_pkgver(pkgbuild):
    ver = re.search(r"^pkgver=(\S+)$", pkgbuild, re.MULTILINE).group(1)
    url = re.search(r'^source=\((.*?)\)$', pkgbuild, re.MULTILINE | re.DOTALL).group(1)
    # PKGBUILDs spell these $pkgname/$pkgver on purpose; resolve them before comparing, or correct style
    # reads as a bug.
    resolved = url.replace("${pkgname}", "babelscribe").replace("$pkgname", "babelscribe")
    resolved = resolved.replace("${pkgver}", ver).replace("$pkgver", ver)
    assert f"babelscribe-{ver}.tar.gz" in resolved, "the source tarball must match pkgver"


def test_licence_and_arch_are_set(pkgbuild):
    assert "license=('MIT')" in pkgbuild
    # Arch: a pure-Python package installs anywhere, so 'any' is correct and not a placeholder.
    assert "arch=('any')" in pkgbuild


def test_runtime_deps_are_declared(pkgbuild):
    """Importing babelscribe needs anyio and mcp at runtime on 3.10+; a missing dep fails at first run."""
    deps = re.search(r"^depends=\((.*?)\)$", pkgbuild, re.MULTILINE | re.DOTALL).group(1)
    names = {d.strip().strip("'\"") for d in deps.split()}
    assert {"python", "python-anyio", "python-mcp"} <= names


def test_srcinfo_matches_the_pkgbuild(pkgbuild):
    """.SRCINFO is what the AUR website renders; if it drifts from PKGBUILD, `yay`/`paru` install the old one."""
    srcinfo = PKGBUILD.parent / ".SRCINFO"
    assert srcinfo.is_file(), "AUR requires .SRCINFO alongside PKGBUILD"
    text = srcinfo.read_text(encoding="utf-8")
    for field in ("pkgver", "sha256sums"):
        # Stop at the closing paren so a multi-line value cannot swallow the functions further down.
        want = re.search(rf"^{field}=\((.*?)\)", pkgbuild, re.MULTILINE | re.DOTALL)
        if want is None:                      # pkgver has no parens
            want = re.search(rf"^{field}=(\S+)", pkgbuild, re.MULTILINE)
        value = want.group(1).strip().strip("'\"")
        assert f"{field} = {value}" in text, f".SRCINFO is stale: {field} should be {value}"
