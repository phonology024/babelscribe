"""Version bump and packaging hashes for a babelscribe release. The order of a release is in RELEASING.md.

  python tools/release.py X.Y.Z          # put the new version everywhere it is pinned, start its CHANGELOG section
  python tools/release.py --after-pypi   # once the version is on PyPI: fill in the Scoop / AUR / Homebrew hashes
  python tools/release.py --check        # show every pinned place and whether it matches the package version

Nothing here commits, tags, uploads or pushes: it only edits files in the working tree.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V = r"\d+\.\d+\.\d+"

# Every place the version is written down, as {file: [pattern, ...]}. In each pattern the version is group 1.
# tests/test_release_tool.py searches the repository for the current version string and fails when it finds one
# that neither a pattern here nor HISTORY below accounts for, so a new pinned file cannot be forgotten.
PINNED: dict[str, list[str]] = {
    "pyproject.toml": [rf'(?m)^version = "({V})"'],
    "babelscribe/__init__.py": [rf'__version__ = "({V})"'],
    "server.json": [rf'"version": "({V})"'],
    "mcpb/manifest.json": [rf'"version": "({V})"'],
    "mcpb/pyproject.toml": [rf'(?m)^version = "({V})"', rf"babelscribe>=({V})"],
    "plugin/.claude-plugin/plugin.json": [rf'"version": "({V})"'],
    "plugin/.mcp.json": [rf"babelscribe==({V})"],
    "plugin/README.md": [rf"babelscribe==({V})", rf"pinned to ({V})"],
    "docs/index.html": [rf'"softwareVersion":"({V})"'],
    "packaging/scoop/babelscribe.json": [rf'"version": "({V})"', rf"babelscribe-({V})-py3-none-any\.whl"],
    "packaging/aur/PKGBUILD": [rf"(?m)^pkgver=({V})"],
    "packaging/aur/.SRCINFO": [rf"pkgver = ({V})", rf"babelscribe-({V})\.tar\.gz::", rf"/babelscribe-({V})\.tar\.gz"],
    "HomebrewFormula/babelscribe.rb": [rf"/babelscribe-({V})\.tar\.gz"],
    "ROADMAP.md": [rf"\*\*PyPI: ({V})\*\*"],
    "docs/llms-full.txt": [rf"\*\*PyPI: ({V})\*\*"],
}
OPTIONAL = {"HomebrewFormula/babelscribe.rb"}   # not every checkout has the formula yet

# Lines that name a version as history, not as "the current version". They are left alone by a bump; the text
# is matched with the version replaced by {v}, so this list does not need editing at each release.
HISTORY: dict[str, list[str]] = {
    "CHANGELOG.md": ["{v}"],
    "ROADMAP.md": ["| **{v}** |", "({v}+)"],
    "docs/llms-full.txt": ["| **{v}** |", "({v}+)"],
    "docker/README.md": ["for {v} or earlier", "after {v},"],
    "packaging/aur/README.md": ["babelscribe-{v}-1-any.pkg.tar.zst"],
    "packaging/homebrew/README.md": ["babelscribe/{v}:", "for {v} ", "`{v}`"],
    "babelscribe/backend.py": ['BINARY_TAG = "v{v}"'],
    "README.md": ["| **{v}** |", "({v}+)"],
}


def current_version() -> str:
    return re.search(rf'__version__ = "({V})"', (ROOT / "babelscribe/__init__.py").read_text(encoding="utf-8")).group(1)


def read(rel: str) -> str | None:
    p = ROOT / rel
    if not p.is_file():
        if rel in OPTIONAL:
            return None
        raise SystemExit(f"{rel} is in the release tool's list but does not exist")
    return p.read_bytes().decode("utf-8")   # bytes: keep the file's own line endings


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_bytes(text.encode("utf-8"))   # bytes: keep the file's own line endings


def pinned_places() -> list[tuple[str, str, str]]:
    """[(file, pattern, version found)] for every pattern; a pattern that matches nothing is an error."""
    out = []
    for rel, patterns in PINNED.items():
        text = read(rel)
        if text is None:
            continue
        for pat in patterns:
            found = re.findall(pat, text)
            if not found:
                raise SystemExit(f"{rel}: nothing matches {pat!r}; the file changed shape, update tools/release.py")
            out += [(rel, pat, v) for v in found]
    return out


def bump(new: str, today: str | None = None) -> list[str]:
    if not re.fullmatch(V, new):
        raise SystemExit(f"{new!r} is not a version like 1.2.3")
    old = current_version()
    if new == old:
        raise SystemExit(f"the package is already {old}")
    today = today or datetime.date.today().isoformat()
    changed = []
    for rel, patterns in PINNED.items():
        text = read(rel)
        if text is None:
            continue
        before = text
        for pat in patterns:
            if not re.search(pat, text):
                raise SystemExit(f"{rel}: nothing matches {pat!r}; the file changed shape, update tools/release.py")
            text = re.sub(pat, lambda m: m.group(0).replace(m.group(1), new), text)
        if rel == "packaging/aur/PKGBUILD":
            text = re.sub(r"(?m)^pkgrel=\d+", "pkgrel=1", text)
        if rel == "packaging/aur/.SRCINFO":
            text = re.sub(r"pkgrel = \d+", "pkgrel = 1", text)
        if rel in ("ROADMAP.md", "docs/llms-full.txt"):
            text = re.sub(rf"(\*\*PyPI: {re.escape(new)}\*\* )\(\d{{4}}-\d\d-\d\d\)", rf"\g<1>({today})", text)
        if text != before:
            write(rel, text)
            changed.append(rel)
    changed += changelog_release(new, today)
    return changed


def changelog_release(new: str, today: str) -> list[str]:
    """Turn '## [Unreleased]' into the new version's section and open a fresh, empty Unreleased above it."""
    text = read("CHANGELOG.md")
    head = "## [Unreleased]"
    if head not in text:
        raise SystemExit("CHANGELOG.md has no '## [Unreleased]' section")
    body = text.split(head, 1)[1].split("\n## [", 1)[0]
    if not body.strip():
        raise SystemExit("CHANGELOG.md: the Unreleased section is empty. Write what changed first.")
    nl = "\r\n" if "\r\n" in text else "\n"
    write("CHANGELOG.md", text.replace(head, f"{head}{nl}{nl}## [{new}] - {today}", 1))
    return ["CHANGELOG.md"]


def pypi_files(version: str, source: str | None = None) -> dict:
    """{'sdist': {url, sha256}, 'wheel': {url, sha256}} for a published version (source: a saved PyPI JSON file)."""
    if source:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
    else:
        url = f"https://pypi.org/pypi/babelscribe/{version}/json"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)
        except OSError as e:
            raise SystemExit(f"cannot read {url}: {e}\nIs {version} on PyPI yet? Offline: save that page and pass "
                             f"--pypi-json FILE.")
    if data["info"]["version"] != version:
        raise SystemExit(f"that PyPI data is for {data['info']['version']}, the package here is {version}")
    out = {}
    for f in data["urls"]:
        kind = {"sdist": "sdist", "bdist_wheel": "wheel"}.get(f["packagetype"])
        if kind:
            out[kind] = {"url": f["url"], "sha256": f["digests"]["sha256"]}
    if set(out) != {"sdist", "wheel"}:
        raise SystemExit(f"PyPI lists {sorted(out)} for {version}; both an sdist and a wheel are needed")
    return out


def after_pypi(source: str | None = None) -> list[str]:
    version = current_version()
    files = pypi_files(version, source)
    sdist, wheel = files["sdist"], files["wheel"]
    edits = {
        "packaging/scoop/babelscribe.json": [
            (r'("url": ")https://files\.pythonhosted\.org/[^"]+(")', rf'\g<1>{wheel["url"]}\g<2>', 1),
            (r'("hash": ")[0-9a-f]{64}(")', rf'\g<1>{wheel["sha256"]}\g<2>', 1)],
        "packaging/aur/PKGBUILD": [(r"(sha256sums=\(')[0-9a-f]{64}('\))", rf"\g<1>{sdist['sha256']}\g<2>", 1)],
        "packaging/aur/.SRCINFO": [(r"(sha256sums = )[0-9a-f]{64}", rf"\g<1>{sdist['sha256']}", 1)],
        # the formula's own url/sha256 come first; the ones after them belong to the vendored resources
        "HomebrewFormula/babelscribe.rb": [
            (r'(url ")https://files\.pythonhosted\.org/[^"]+(")', rf'\g<1>{sdist["url"]}\g<2>', 1),
            (r'(sha256 ")[0-9a-f]{64}(")', rf'\g<1>{sdist["sha256"]}\g<2>', 1)],
    }
    changed = []
    for rel, subs in edits.items():
        text = read(rel)
        if text is None:
            continue
        before = text
        for pat, repl, count in subs:
            text, n = re.subn(pat, repl, text, count=count)
            if not n:
                raise SystemExit(f"{rel}: nothing matches {pat!r}; the file changed shape, update tools/release.py")
        if text != before:
            write(rel, text)
            changed.append(rel)
    return changed


def check() -> int:
    version = current_version()
    bad = 0
    for rel, _, found in pinned_places():
        ok = found == version
        bad += not ok
        print(f"  {'ok ' if ok else 'OLD'}  {found:8} {rel}")
    print(f"package version {version}: " + ("every pinned place matches" if not bad else f"{bad} place(s) differ"))
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", nargs="?", help="the new version, e.g. 1.2.3")
    ap.add_argument("--after-pypi", action="store_true", help="fill the packaging hashes for the current version")
    ap.add_argument("--pypi-json", help="with --after-pypi: a saved https://pypi.org/pypi/babelscribe/X.Y.Z/json")
    ap.add_argument("--check", action="store_true", help="list the pinned places, change nothing")
    a = ap.parse_args(argv)
    if a.check:
        return check()
    if a.after_pypi:
        changed = after_pypi(a.pypi_json)
        print("\n".join(f"  updated {c}" for c in changed) or "  nothing to change: the hashes already match PyPI")
        print("Next: run the tests, open the packaging PR (RELEASING.md, step 7).")
        return 0
    if not a.version:
        ap.error("give a version, --after-pypi or --check")
    old = current_version()
    changed = bump(a.version)
    print(f"{old} -> {a.version}")
    print("\n".join(f"  updated {c}" for c in changed))
    print("Not done by this tool: the ROADMAP release table row and the packaging hashes (after PyPI).\n"
          "Next: review the diff, run the tests, open the release PR (RELEASING.md, step 2).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
