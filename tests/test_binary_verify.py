"""The one thing babelscribe downloads and executes is checked: pinned release, sha256 before unpacking (#53)."""
from pathlib import Path

from babelscribe import backend


def _fake_release(monkeypatch, tmp_path, name="whisper-cli-linux-x64-cpu.zip", payload=b"binary", releases=None):
    """A release that serves one zip holding a whisper-cli. Returns the zip's real sha256."""
    import hashlib
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(backend.EXE, payload)
        z.writestr("LICENSE-whisper.cpp", "MIT")
    data = buf.getvalue()
    monkeypatch.setattr(backend, "CACHE", tmp_path / "home")
    monkeypatch.setattr(backend, "RELEASES", releases or backend.DEFAULT_RELEASES)
    monkeypatch.setattr(backend, "asset_name", lambda flavor=None: name)
    monkeypatch.setattr(backend.urllib.request, "urlopen", lambda url: io.BytesIO(data))
    monkeypatch.delenv("BABELSCRIBE_SKIP_VERIFY", raising=False)
    return hashlib.sha256(data).hexdigest()


def test_fetch_binary_installs_a_zip_with_the_pinned_digest(monkeypatch, tmp_path):
    name = "whisper-cli-linux-x64-cpu.zip"
    digest = _fake_release(monkeypatch, tmp_path)
    monkeypatch.setitem(backend.SHA256, name, digest)
    exe = backend.fetch_binary("cpu")
    assert exe.read_bytes() == b"binary"
    assert not list((tmp_path / "home" / "bin").glob("*.part"))
    origin = backend.binary_origin(exe)
    assert backend.BINARY_TAG in origin and "checksum verified" in origin and "unchanged" in origin
    exe.write_bytes(b"something else")                       # corrupted or swapped after the download
    assert "CHANGED" in backend.binary_origin(exe)


def test_fetch_binary_refuses_a_wrong_digest_and_leaves_nothing(monkeypatch, tmp_path):
    import pytest
    _fake_release(monkeypatch, tmp_path)                     # the real table has another digest for this name
    with pytest.raises(SystemExit) as e:
        backend.fetch_binary("cpu")
    assert "checksum mismatch" in str(e.value) and "nothing was installed" in str(e.value)
    assert not [f for f in (tmp_path / "home").rglob("*") if f.is_file()], "nothing may stay in the cache"


def test_fetch_binary_holds_a_mirror_to_the_same_digests_unless_told_not_to(monkeypatch, tmp_path):
    import pytest
    mirror = "https://example.invalid/mirror"
    _fake_release(monkeypatch, tmp_path, releases=mirror)
    with pytest.raises(SystemExit) as e:                     # an official name with other bytes: refused
        backend.fetch_binary("cpu")
    assert "BABELSCRIBE_SKIP_VERIFY" in str(e.value)
    _fake_release(monkeypatch, tmp_path, name="whisper-cli-linux-arm64-cpu.zip", releases=mirror)
    with pytest.raises(SystemExit) as e:                     # a build the project does not publish: no digest
        backend.fetch_binary("cpu")
    assert "BABELSCRIBE_SKIP_VERIFY" in str(e.value)
    monkeypatch.setenv("BABELSCRIBE_SKIP_VERIFY", "1")
    exe = backend.fetch_binary("cpu")
    assert exe.read_bytes() == b"binary" and "NOT verified" in backend.binary_origin(exe)


def test_binary_origin_for_own_builds_and_old_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "CACHE", tmp_path / "home")
    own = tmp_path / "build" / backend.EXE
    own.parent.mkdir(parents=True); own.write_bytes(b"x")
    assert "your own build" in backend.binary_origin(own)
    old = tmp_path / "home" / "bin" / "whisper-cli-linux-x64-cpu" / backend.EXE
    old.parent.mkdir(parents=True); old.write_bytes(b"x")
    assert "release unknown" in backend.binary_origin(old)


def test_downloads_are_pinned_to_a_release_tag_not_latest():
    assert "/latest/" not in backend.DEFAULT_RELEASES and backend.DEFAULT_RELEASES.endswith(backend.BINARY_TAG)
    assert set(backend.SHA256) == {f"whisper-cli-{s}-{a}-{f}.zip" for s, a, f in backend.ASSETS}


def test_digest_table_matches_the_pinned_release():
    """Network test: the digests in backend.SHA256 are the ones GitHub reports for BINARY_TAG's assets."""
    import json
    import urllib.request
    import pytest
    url = f"https://api.github.com/repos/phonology024/babelscribe/releases/tags/{backend.BINARY_TAG}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "babelscribe-tests"}),
                                    timeout=10) as r:
            assets = json.load(r)["assets"]
    except OSError as e:     # offline, or the anonymous API rate limit on a shared CI address
        pytest.skip(f"cannot reach the GitHub API: {e}")
    published = {a["name"]: (a.get("digest") or "").removeprefix("sha256:") for a in assets}
    for name, digest in backend.SHA256.items():
        assert published.get(name) == digest, name


def test_a_model_download_cut_short_is_not_kept(monkeypatch, tmp_path):
    import urllib.error
    import pytest
    from babelscribe import models
    monkeypatch.setattr(models, "MODELS", tmp_path)

    def cut_short(url, dst):
        Path(dst).write_bytes(b"half")
        raise urllib.error.ContentTooShortError("retrieval incomplete", None)
    monkeypatch.setattr(models.urllib.request, "urlretrieve", cut_short)
    with pytest.raises(SystemExit) as e:
        models.ensure("tiny")
    assert "cut short" in str(e.value) and not list(tmp_path.iterdir())
