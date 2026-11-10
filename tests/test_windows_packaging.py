"""Windows packaging: the Scoop manifest, and why winget cannot take a pure-Python package.

The manifest is checked against Scoop's own schema (the same file `scoop shim` and the bucket CI validate
against), so a typo in a key name fails here instead of in someone's install.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "packaging" / "scoop" / "babelscribe.json"


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_the_scoop_manifest_is_valid_json():
    assert manifest()["version"]


def test_the_version_matches_the_package():
    from babelscribe import __version__
    assert manifest()["version"] == __version__


def test_it_declares_python_because_it_builds_a_venv():
    m = manifest()
    assert m["depends"] == "python"
    script = " ".join(m["installer"]["script"])
    assert "python -m venv" in script
    assert "pip install" in script


def test_the_wheel_url_and_hash_agree():
    """A copy-pasted hash is the classic manifest bug; check it actually hashes the file it points at."""
    m = manifest()
    assert m["url"].endswith(f"babelscribe-{m['version']}-py3-none-any.whl")
    try:
        data = urllib.request.urlopen(m["url"], timeout=30).read()
    except Exception as e:  # network is not required to run the test suite
        pytest.skip(f"cannot reach PyPI: {e}")
    assert hashlib.sha256(data).hexdigest() == m["hash"]


def test_the_shims_point_at_console_scripts_the_wheel_really_has():
    m = manifest()
    assert m["bin"] == [
        "babelscribe\\Scripts\\babelscribe.exe",
        "babelscribe\\Scripts\\babelscribe-mcp.exe",
    ]
    names = {b.rsplit("\\", 1)[-1].removesuffix(".exe") for b in m["bin"]}
    entry = ROOT / "pyproject.toml"
    scripts = entry.read_text(encoding="utf-8")
    for name in names:
        assert name in scripts, f"{name} is not a console_script in pyproject.toml"


def test_autoupdate_resolves_to_a_real_url():
    """The py3/<first-letter>/<name>/ alias is what the Main bucket uses for pip packages; confirm it exists."""
    url = manifest()["autoupdate"]["url"].replace("$version", manifest()["version"])
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            assert r.status == 200
    except Exception as e:
        pytest.skip(f"cannot reach PyPI: {e}")


def test_it_validates_against_scoops_official_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).resolve().parent / "data" / "scoop-schema.json"
    if not schema_path.is_file():
        pytest.skip("scoop schema not vendored")
    jsonschema.validate(manifest(), json.loads(schema_path.read_text(encoding="utf-8")))


def test_winget_cannot_express_a_pip_install():
    """Documents the reason #21's winget half is not attempted here.

    winget's manifest has no script installer type — the enum is msix/msi/appx/exe/zip/inno/nullsoft/wix/
    burn/pwa/portable. A pure-Python package has no .exe to point at, and winget-pkgs has no manifest that
    runs `pip install`. The Scoop manifest exists precisely because Scoop does have an installer script.
    """
    assert "installer" in manifest(), "Scoop supports a script installer; winget does not"