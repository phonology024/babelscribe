"""tools/release.py (#54): one command puts a new version everywhere it is pinned, and the list of places is complete."""
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release_tool", ROOT / "tools" / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout (sdist): the file list comes from git")
    return [f for f in out.splitlines() if (ROOT / f).is_file()]


def test_every_pinned_place_has_the_package_version():
    from babelscribe import __version__
    places = release.pinned_places()
    assert len(places) >= 18
    assert [(rel, v) for rel, _, v in places if v != __version__] == []


def test_no_file_pins_the_version_without_the_tool_knowing():
    """Search the whole repository for the current version. Each hit must be a place the tool rewrites, or a
    line listed as history. A new manifest that pins the version fails here until it is added to PINNED."""
    version = release.current_version()
    unknown = []
    for rel in tracked_files():
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if version not in text or rel == "CHANGELOG.md":
            continue
        covered = text
        for pat in release.PINNED.get(rel, []):
            covered = re.sub(pat, lambda m: m.group(0).replace(m.group(1), "<pinned>"), covered)
        for known in release.HISTORY.get(rel, []):
            covered = covered.replace(known.format(v=version), "<history>")
        unknown += [f"{rel}: {line.strip()[:120]}" for line in covered.splitlines() if version in line]
    assert unknown == [], "add these to PINNED (or HISTORY) in tools/release.py"


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """The release tool pointed at a copy of the files it edits."""
    for rel in [*release.PINNED, "CHANGELOG.md"]:
        if (ROOT / rel).is_file():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, tmp_path / rel)
    monkeypatch.setattr(release, "ROOT", tmp_path)
    version = release.current_version()      # right after a release the real Unreleased section is empty
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n### Added\n- something new\n\n## [{version}] - 2026-01-01\n\n- older\n",
        encoding="utf-8")
    return tmp_path


def test_bump_changes_every_place_and_only_the_version(copy):
    old = release.current_version()
    changed = release.bump("9.8.7", today="2030-01-02")
    assert release.current_version() == "9.8.7"
    assert {v for _, _, v in release.pinned_places()} == {"9.8.7"}
    assert set(changed) >= {"pyproject.toml", "server.json", "packaging/scoop/babelscribe.json", "CHANGELOG.md"}
    assert json.loads((copy / "server.json").read_text(encoding="utf-8"))["version"] == "9.8.7"   # still valid JSON
    assert json.loads((copy / "packaging/scoop/babelscribe.json").read_text(encoding="utf-8"))["version"] == "9.8.7"
    roadmap = (copy / "ROADMAP.md").read_text(encoding="utf-8")
    assert "**PyPI: 9.8.7** (2030-01-02)" in roadmap
    assert f"| **{old}** |" in roadmap, "the history row of the previous release is left alone"
    log = (copy / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]\n\n## [9.8.7] - 2030-01-02\n\n### Added\n- something new" in log and f"## [{old}]" in log


def test_bump_refuses_bad_input(copy):
    for bad in ("1.2", "v1.2.3", release.current_version()):
        with pytest.raises(SystemExit):
            release.bump(bad)
    (copy / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        release.bump("9.8.7")
    assert "Unreleased section is empty" in str(e.value)


def test_after_pypi_fills_the_packaging_hashes(copy, tmp_path):
    version = release.current_version()
    wheel = f"https://files.pythonhosted.org/packages/aa/bb/cc/babelscribe-{version}-py3-none-any.whl"
    sdist = f"https://files.pythonhosted.org/packages/dd/ee/ff/babelscribe-{version}.tar.gz"
    saved = tmp_path / "pypi.json"
    saved.write_text(json.dumps({"info": {"version": version}, "urls": [
        {"packagetype": "bdist_wheel", "url": wheel, "digests": {"sha256": "1" * 64}},
        {"packagetype": "sdist", "url": sdist, "digests": {"sha256": "2" * 64}}]}), encoding="utf-8")
    changed = release.after_pypi(str(saved))
    assert set(changed) >= {"packaging/scoop/babelscribe.json", "packaging/aur/PKGBUILD", "packaging/aur/.SRCINFO"}
    scoop = json.loads((copy / "packaging/scoop/babelscribe.json").read_text(encoding="utf-8"))
    assert (scoop["url"], scoop["hash"]) == (wheel, "1" * 64)
    assert f"sha256sums=('{'2' * 64}')" in (copy / "packaging/aur/PKGBUILD").read_text(encoding="utf-8")
    assert f"sha256sums = {'2' * 64}" in (copy / "packaging/aur/.SRCINFO").read_text(encoding="utf-8")
    assert release.after_pypi(str(saved)) == [], "a second run has nothing left to change"
    saved.write_text(json.dumps({"info": {"version": "0.0.1"}, "urls": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        release.after_pypi(str(saved))


def test_the_changelog_is_kept():
    """The release PR must touch CHANGELOG.md: there is always an Unreleased section, and the current version has
    its own section with a date."""
    log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in log
    assert re.search(rf"^## \[{re.escape(release.current_version())}\] - \d{{4}}-\d\d-\d\d$", log, re.MULTILINE)
