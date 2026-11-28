"""Downloads continue where they stopped, and nothing is used unless it is whole and right.

The server here is a real one on this computer that cuts connections off part way, as a flaky network does."""
import hashlib
import io
import os
import socket
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from babelscribe import backend, download, models

DATA = bytes(range(256)) * 4000                      # 1 MB, every offset recognisable
SHA = hashlib.sha256(DATA).hexdigest()


class Server:
    """Serves `files`. Each request takes the next step of `plan` (the last one repeats):
    "ok", ("cut", n) = announce everything, send n bytes, drop the line; "norange" = answer 200 with the whole file;
    "wrong-offset" = a 206 that starts somewhere else; an int = that HTTP status."""

    def __init__(self, files):
        self.files, self.plan, self.asked = dict(files), ["ok"], []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                rng = self.headers.get("Range")
                outer.asked.append((self.path, rng))
                step = outer.plan.pop(0) if len(outer.plan) > 1 else outer.plan[0]
                data = outer.files.get(self.path.lstrip("/"))
                if isinstance(step, int) or data is None:
                    self.send_error(step if isinstance(step, int) else 404)
                    return
                start = int(rng[6:-1]) if rng and step != "norange" else 0
                if start >= len(data) and start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{len(data)}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = data[start:]
                self.send_response(206 if start else 200)
                if start:
                    shown = 0 if step == "wrong-offset" else start
                    self.send_header("Content-Range", f"bytes {shown}-{len(data) - 1}/{len(data)}")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if isinstance(step, tuple):
                    self.wfile.write(body[:step[1]])
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection = True
                    return
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.handle_error = lambda *a: None
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(download, "SLEEP", lambda s: None)
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    s = Server({"f.bin": DATA})
    yield s
    s.close()


def ranges(server):
    return [r for _, r in server.asked]


def test_a_dropped_connection_is_continued_from_the_byte_it_reached(server, tmp_path):
    server.plan = [("cut", 300_000), ("cut", 200_000), "ok"]
    said = []
    part = tmp_path / "f.part"
    assert download.fetch(server.url + "/f.bin", part, SHA, "the file", said.append) == SHA
    assert part.read_bytes() == DATA
    assert ranges(server) == [None, "bytes=300000-", "bytes=500000-"]
    assert sum("interrupted" in m for m in said) == 2


def test_the_next_run_continues_what_an_earlier_one_left(server, tmp_path):
    part = tmp_path / "f.part"
    part.write_bytes(DATA[:700_000])
    said = []
    download.fetch(server.url + "/f.bin", part, SHA, "the file", said.append)
    assert ranges(server) == ["bytes=700000-"] and part.read_bytes() == DATA and "continuing" in said[0]


def test_giving_up_keeps_the_part_and_says_so(server, tmp_path):
    server.plan = [("cut", 400_000), 503]                       # some bytes, then the server stays broken
    part = tmp_path / "f.part"
    with pytest.raises(SystemExit) as e:
        download.fetch(server.url + "/f.bin", part, SHA, "the file", lambda m: None)
    assert "HTTP 503" in str(e.value) and "kept" in str(e.value) and "continue" in str(e.value)
    assert part.read_bytes() == DATA[:400_000]
    assert len(server.asked) == 1 + download.ATTEMPTS
    server.plan = ["ok"]
    download.fetch(server.url + "/f.bin", part, SHA, "the file", lambda m: None)
    assert part.read_bytes() == DATA and ranges(server)[-1] == "bytes=400000-"


def test_attempts_that_bring_new_bytes_are_not_counted_against_it(server, tmp_path):
    server.plan = [("cut", 50_000)] * 15 + ["ok"]               # more drops than ATTEMPTS, each one moving forward
    download.fetch(server.url + "/f.bin", tmp_path / "f.part", SHA, "the file", lambda m: None)
    assert (tmp_path / "f.part").read_bytes() == DATA


def test_a_server_that_ignores_ranges_gets_a_fresh_file_not_a_doubled_one(server, tmp_path):
    part = tmp_path / "f.part"
    part.write_bytes(DATA[:100_000])
    server.plan = ["norange"]
    download.fetch(server.url + "/f.bin", part, SHA, "the file", lambda m: None)
    assert part.read_bytes() == DATA


def test_a_server_that_ignores_ranges_and_keeps_cutting_at_one_place_is_given_up_on(server, tmp_path):
    server.plan = [("cut", 100_000)]
    real = server.httpd.RequestHandlerClass.do_GET

    def no_range(self):
        del self.headers["Range"]
        real(self)
    server.httpd.RequestHandlerClass.do_GET = no_range
    with pytest.raises(SystemExit):
        download.fetch(server.url + "/f.bin", tmp_path / "f.part", SHA, "the file", lambda m: None)
    assert len(server.asked) == 1 + download.ATTEMPTS


def test_a_continuation_at_the_wrong_offset_is_thrown_away(server, tmp_path):
    part = tmp_path / "f.part"
    part.write_bytes(DATA[:100_000])
    server.plan = ["wrong-offset", "ok"]
    download.fetch(server.url + "/f.bin", part, SHA, "the file", lambda m: None)
    assert part.read_bytes() == DATA and ranges(server) == ["bytes=100000-", None]


def test_a_part_with_wrong_bytes_is_downloaded_again_once_and_comes_out_right(server, tmp_path):
    part = tmp_path / "f.part"
    part.write_bytes(b"x" * 100_000)                            # damaged: the sum cannot match after continuing it
    said = []
    download.fetch(server.url + "/f.bin", part, SHA, "the file", said.append)
    assert part.read_bytes() == DATA and any("from the beginning" in m for m in said)
    assert ranges(server) == ["bytes=100000-", None]


@pytest.mark.parametrize("wrong", [b"y" * len(DATA), b"z" * (len(DATA) + 5)], ids=["same-length", "longer"])
def test_a_part_that_is_as_long_or_longer_than_the_file_is_replaced(server, tmp_path, wrong):
    part = tmp_path / "f.part"
    part.write_bytes(wrong)                                     # the server answers 416: nothing at that offset
    download.fetch(server.url + "/f.bin", part, SHA, "the file", lambda m: None)
    assert part.read_bytes() == DATA


def test_a_complete_part_is_used_without_asking_the_server(server, tmp_path):
    part = tmp_path / "f.part"
    part.write_bytes(DATA)
    assert download.fetch(server.url + "/f.bin", part, SHA, "the file", lambda m: None) == SHA
    assert not server.asked


def test_a_whole_file_with_the_wrong_checksum_is_deleted(server, tmp_path):
    part = tmp_path / "f.part"
    with pytest.raises(download.ChecksumMismatch) as e:
        download.fetch(server.url + "/f.bin", part, "0" * 64, "the file", lambda m: None)
    assert e.value.got == SHA and not part.exists() and len(server.asked) == 1


def test_without_a_checksum_nothing_is_ever_joined_or_kept(server, tmp_path):
    part = tmp_path / "f.part"
    part.write_bytes(b"left over")
    server.plan = [("cut", 300_000), "ok"]
    assert download.fetch(server.url + "/f.bin", part, None, "the file", lambda m: None) == SHA
    assert part.read_bytes() == DATA and ranges(server) == [None, None]
    server.plan = [("cut", 300_000)]
    with pytest.raises(SystemExit) as e:
        download.fetch(server.url + "/f.bin", part, None, "the file", lambda m: None)
    assert not part.exists() and "kept" not in str(e.value)


@pytest.mark.parametrize("status", [408, 429, 500, 502])
def test_a_busy_server_is_asked_again(server, tmp_path, status):
    server.plan = [status, "ok"]
    download.fetch(server.url + "/f.bin", tmp_path / "f.part", SHA, "the file", lambda m: None)


def test_404_and_a_refusal_are_not_retried(server, tmp_path):
    with pytest.raises(download.NotFound):
        download.fetch(server.url + "/nothing", tmp_path / "f.part", SHA, "the file", lambda m: None)
    server.plan = [403]
    with pytest.raises(SystemExit) as e:
        download.fetch(server.url + "/f.bin", tmp_path / "f.part", SHA, "the file", lambda m: None)
    assert "HTTP 403" in str(e.value) and len(server.asked) == 2


def test_no_network_at_all_ends_with_a_message(monkeypatch, tmp_path):
    waits = []
    monkeypatch.setattr(download, "SLEEP", waits.append)

    def offline(*a, **k):
        raise urllib.error.URLError("getaddrinfo failed")
    monkeypatch.setattr(download.urllib.request, "urlopen", offline)
    with pytest.raises(SystemExit) as e:
        download.fetch("https://example.invalid/f", tmp_path / "f.part", SHA, "the file", lambda m: None)
    assert "getaddrinfo failed" in str(e.value) and "internet connection" in str(e.value)
    assert len(waits) == download.ATTEMPTS - 1 and sum(waits) < 60


@pytest.mark.parametrize("failures", [2, 99], ids=["passes-later", "always"])
def test_a_certificate_failure_is_tried_again_with_the_check_still_on(server, tmp_path, monkeypatch, failures):
    real, calls = download.urllib.request.urlopen, []

    def flaky(req, **kwargs):
        calls.append(kwargs)
        if len(calls) <= failures:
            raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get issuer certificate"))
        return real(req, **kwargs)
    monkeypatch.setattr(download.urllib.request, "urlopen", flaky)
    part = tmp_path / "f.part"
    if failures < download.ATTEMPTS:
        download.fetch(server.url + "/f.bin", part, SHA, "the file", lambda m: None)
        assert part.read_bytes() == DATA
    else:
        with pytest.raises(SystemExit) as e:
            download.fetch(server.url + "/f.bin", part, SHA, "the file", lambda m: None)
        assert "date and time" in str(e.value) and len(calls) == download.ATTEMPTS
    for k in calls:
        assert set(k) <= {"timeout", "context"}
        if "context" in k:
            assert k["context"].verify_mode == ssl.CERT_REQUIRED and k["context"].check_hostname


def test_after_a_certificate_failure_the_windows_roots_are_tried_on_their_own(server, tmp_path, monkeypatch):
    real, used = download.urllib.request.urlopen, []
    roots = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(download, "_roots_only", lambda: roots)

    def only_with_roots(req, timeout=None, context=None):
        used.append(context)
        if context is not roots:
            raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get issuer certificate"))
        return real(req, timeout=timeout)
    monkeypatch.setattr(download.urllib.request, "urlopen", only_with_roots)
    server.plan = [("cut", 300_000), "ok"]                       # and it is still used for the continuation
    download.fetch(server.url + "/f.bin", tmp_path / "f.part", SHA, "the file", lambda m: None)
    assert used == [None, roots, roots]


def test_the_roots_only_check_is_a_full_check():
    ctx = download._roots_only()
    if not hasattr(ssl, "enum_certificates"):
        assert ctx is None
        return
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname and ctx.cert_store_stats()["x509_ca"] > 0


def test_a_file_mirror_without_the_file_is_not_found(tmp_path):
    with pytest.raises(download.NotFound):
        download.fetch((tmp_path / "no-such.zip").as_uri(), tmp_path / "f.part", SHA, "the file", lambda m: None)
    src = tmp_path / "f.zip"
    src.write_bytes(DATA)
    assert download.fetch(src.as_uri(), tmp_path / "g.part", SHA, "the file", lambda m: None) == SHA


def test_a_full_disk_keeps_what_there_is_and_is_not_retried(server, tmp_path, monkeypatch):
    real = open

    class Full:
        def __init__(self, f):
            self.f = f

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.f.close()

        def write(self, b):
            raise OSError(28, "No space left on device")

    def opened(path, mode="r", *a, **k):
        f = real(path, mode, *a, **k)
        return Full(f) if str(path).endswith("f.part") and mode in ("wb", "ab") else f
    monkeypatch.setattr(download, "open", opened, raising=False)
    with pytest.raises(SystemExit) as e:
        download.fetch(server.url + "/f.bin", tmp_path / "f.part", SHA, "the file", lambda m: None)
    assert "No space left" in str(e.value) and "disk space" in str(e.value) and len(server.asked) == 1


def test_ctrl_c_keeps_a_checkable_part_and_removes_one_that_cannot_be_checked(server, tmp_path, monkeypatch):
    def stop(url, part, resume, tls):
        part.write_bytes(DATA[:10])
        raise KeyboardInterrupt
    monkeypatch.setattr(download, "_attempt", stop)
    for sha, stays in ((SHA, True), (None, False)):
        part = tmp_path / f"{stays}.part"
        with pytest.raises(KeyboardInterrupt):
            download.fetch(server.url + "/f.bin", part, sha, "the file", lambda m: None)
        assert part.exists() is stays


HOLD = """
import sys, time
from pathlib import Path
from babelscribe import download
with download.lock(Path(sys.argv[1]), "x"):
    print("locked", flush=True)
    time.sleep(60)
"""


def test_the_lock_makes_a_second_download_wait_and_a_killed_process_lets_go(tmp_path, monkeypatch):
    path = tmp_path / "a.lock"
    root = str(Path(download.__file__).resolve().parent.parent)
    other = subprocess.Popen([sys.executable, "-c", HOLD, str(path)], stdout=subprocess.PIPE, text=True,
                             env={**os.environ, "PYTHONPATH": root})
    try:
        assert other.stdout.readline().strip() == "locked"
        said, naps = [], []

        def nap(s):
            naps.append(s)
            if len(naps) == 3:
                other.kill()                                    # killed, not closed: the system must drop the lock
                other.wait()
            assert len(naps) < 200
        monkeypatch.setattr(download, "SLEEP", nap)
        with download.lock(path, "the file", said.append) as waited:
            assert waited and len(naps) >= 3 and len(said) == 1 and "waiting" in said[0]
    finally:
        other.kill()
        other.wait()
    with download.lock(path, "the file") as waited:
        assert not waited


def test_two_threads_do_not_download_the_same_model_twice(server, tmp_path, monkeypatch):
    monkeypatch.setattr(download, "SLEEP", lambda s: __import__("time").sleep(0.01))
    monkeypatch.setattr(models, "MODELS", tmp_path)
    monkeypatch.setattr(models, "GGML", server.url + "/f.bin?{revision}{name}")
    monkeypatch.setitem(models.SHA256, "tiny", SHA)
    server.files = {f"f.bin?{models.GGML_REVISION}tiny": DATA}
    got = []
    threads = [threading.Thread(target=lambda: got.append(models.ensure("tiny"))) for _ in range(4)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert len(got) == 4 and got[0].read_bytes() == DATA and len(server.asked) == 1


def model_server(server, monkeypatch, tmp_path, at="pinned"):
    monkeypatch.setattr(models, "MODELS", tmp_path / "models")
    monkeypatch.setattr(models, "GGML", server.url + "/{revision}/{name}")
    monkeypatch.setattr(models, "GGML_REVISION", "pinned")
    monkeypatch.setitem(models.SHA256, "tiny", SHA)
    server.files = {f"{at}/tiny": DATA}


def test_a_model_cut_short_in_one_run_is_finished_in_the_next(server, tmp_path, monkeypatch):
    model_server(server, monkeypatch, tmp_path)
    server.plan = [("cut", 600_000), 500]
    with pytest.raises(SystemExit) as e:
        models.ensure("tiny")
    assert "model tiny" in str(e.value) and not models.path_for("tiny").exists(), "half a model has no model name"
    server.plan = ["ok"]
    assert models.ensure("tiny").read_bytes() == DATA and ranges(server)[-1] == "bytes=600000-"
    assert not list(models.MODELS.glob("*.part"))


def test_a_model_that_is_not_the_expected_file_is_refused(server, tmp_path, monkeypatch):
    model_server(server, monkeypatch, tmp_path)
    monkeypatch.setitem(models.SHA256, "tiny", "0" * 64)
    with pytest.raises(SystemExit) as e:
        models.ensure("tiny")
    assert "checksum mismatch" in str(e.value) and not models.path_for("tiny").exists()
    assert not list(models.MODELS.glob("*.part"))


def test_a_rewritten_model_repository_falls_back_to_main_with_the_same_checksum(server, tmp_path, monkeypatch):
    model_server(server, monkeypatch, tmp_path, at="main")
    assert models.ensure("tiny").read_bytes() == DATA
    server.files = {}
    models.path_for("tiny").unlink()
    with pytest.raises(SystemExit) as e:
        models.ensure("tiny")
    assert "HTTP 404" in str(e.value)


def release_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(backend.EXE, b"binary" * 50_000)
        z.writestr("ggml.dll", os.urandom(100_000))
    return buf.getvalue()


def binary_server(server, monkeypatch, tmp_path):
    data = release_zip()
    name = "whisper-cli-linux-x64-cpu.zip"
    server.files = {name: data}
    monkeypatch.setattr(backend, "CACHE", tmp_path / "home")
    monkeypatch.setattr(backend, "RELEASES", server.url)
    monkeypatch.setattr(backend, "asset_name", lambda flavor=None: name)
    monkeypatch.setitem(backend.SHA256, name, hashlib.sha256(data).hexdigest())
    monkeypatch.delenv("BABELSCRIBE_SKIP_VERIFY", raising=False)
    monkeypatch.delenv("BABELSCRIBE_WHISPER_BIN", raising=False)
    monkeypatch.setattr(backend.shutil, "which", lambda name: None)
    return name


def test_whisper_cli_cut_off_midway_is_continued(server, tmp_path, monkeypatch):
    binary_server(server, monkeypatch, tmp_path)
    server.plan = [("cut", 40_000), "ok"]
    exe = backend.fetch_binary("cpu")
    assert exe.read_bytes() == b"binary" * 50_000 and ranges(server) == [None, "bytes=40000-"]
    assert not list((tmp_path / "home" / "bin").glob("*.part"))


def test_an_install_killed_while_unpacking_leaves_nothing_that_looks_installed(server, tmp_path, monkeypatch):
    binary_server(server, monkeypatch, tmp_path)
    real = zipfile.ZipFile.extractall

    def killed(self, path):
        self.extract(backend.EXE, path)                         # the program is out, its library is not
        raise KeyboardInterrupt
    monkeypatch.setattr(zipfile.ZipFile, "extractall", killed)
    with pytest.raises(KeyboardInterrupt):
        backend.fetch_binary("cpu")
    with pytest.raises(FileNotFoundError):
        backend.find_binary(download=False)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", real)
    asked = len(server.asked)
    exe = backend.fetch_binary("cpu")
    assert (exe.parent / "ggml.dll").is_file() and len(server.asked) == asked, "the checked zip was not fetched again"
    assert "unchanged" in backend.binary_origin(exe)


def test_a_full_disk_while_unpacking_keeps_the_zip_and_installs_nothing(server, tmp_path, monkeypatch):
    name = binary_server(server, monkeypatch, tmp_path)

    def full(self, path):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(zipfile.ZipFile, "extractall", full)
    with pytest.raises(SystemExit) as e:
        backend.fetch_binary("cpu")
    assert "No space left" in str(e.value) and "kept" in str(e.value)
    assert not (tmp_path / "home" / "bin" / name[:-4]).exists()
    assert len(list((tmp_path / "home" / "bin").glob("*.part"))) == 1


def test_a_new_pinned_build_never_continues_the_old_ones_part(server, tmp_path, monkeypatch):
    name = binary_server(server, monkeypatch, tmp_path)
    folder = tmp_path / "home" / "bin"
    folder.mkdir(parents=True)
    for old in (f"{name}.part", f"{name}.0123456789ab.part"):
        (folder / old).write_bytes(b"old build")
    backend.fetch_binary("cpu")
    assert ranges(server) == [None] and not list(folder.glob("*.part"))


def test_the_pinned_model_digests_are_the_ones_hugging_face_lists():
    import json
    url = f"https://huggingface.co/api/models/ggerganov/whisper.cpp/tree/{models.GGML_REVISION}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "babelscribe-tests"}),
                                    timeout=20) as r:
            listed = {f["path"]: f.get("lfs", {}).get("oid") for f in json.load(r)}
    except (OSError, ValueError) as e:
        pytest.skip(f"no network: {e}")
    assert {n: listed.get(f"ggml-{n}.bin") for n in models.SHA256} == models.SHA256
