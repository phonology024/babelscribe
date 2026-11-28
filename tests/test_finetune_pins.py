"""Converting a fine-tune runs a downloaded script and loads downloaded weights, so every one of them is one fixed file:
the converter and its filter table by sha256, each fine-tune by its repository commit.

torch, transformers and huggingface_hub are stand-ins and nothing downloaded is executed here: the test records what
would have been run."""
import hashlib
import json
import re
import sys
import types
import urllib.error
import urllib.request

import pytest

from babelscribe import download, models

from test_download import Server

CONVERTER = b"from transformers import W\nmodel = " + models.LOADS.encode() + b"print('done')\n"
MEL = bytes(range(256)) * 16


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def conversion(monkeypatch, tmp_path):
    monkeypatch.setattr(download, "SLEEP", lambda s: None)
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    server = Server({"convert.py": CONVERTER, "mel.npz": MEL})
    monkeypatch.setattr(models, "MODELS", tmp_path / "models")
    monkeypatch.setattr(models, "CONVERTER", server.url + "/convert.py")
    monkeypatch.setattr(models, "CONVERTER_SHA256", sha(CONVERTER))
    monkeypatch.setattr(models, "MEL_FILTERS", server.url + "/mel.npz")
    monkeypatch.setattr(models, "MEL_FILTERS_SHA256", sha(MEL))
    asked, ran = [], []
    hub = types.ModuleType("huggingface_hub")
    hub.snapshot_download = lambda repo, **kw: (asked.append((repo, kw)), str(kw["local_dir"]))[1]
    for name, module in (("torch", types.ModuleType("torch")), ("transformers", types.ModuleType("transformers")),
                         ("huggingface_hub", hub)):
        monkeypatch.setitem(sys.modules, name, module)

    def run(cmd, **kw):
        if cmd[0] == sys.executable:                 # the converter: keep what it holds at the moment it would run
            script, _, whisper, out = cmd[1:]
            ran.append((cmd, open(script, "rb").read(),
                        open(f"{whisper}/whisper/assets/mel_filters.npz", "rb").read()))
            open(f"{out}/ggml-model.bin", "wb").write(b"f32 model")
        else:
            assert cmd[0] != "git", "nothing is cloned any more"
            open(cmd[2], "wb").write(b"half a quantized")
            raise KeyboardInterrupt
    monkeypatch.setattr(models.subprocess, "run", run)
    work = models.MODELS / "_thai-pathumma"
    yield types.SimpleNamespace(server=server, asked=asked, ran=ran, work=work)
    server.close()


def test_the_checked_converter_runs_with_the_checked_filter_table_and_the_pinned_weights(conversion):
    out = models.ensure("thai-pathumma")
    assert out.read_bytes() == b"f32 model"
    (cmd, script, mel), = conversion.ran
    assert script == CONVERTER.replace(b"(dir_model)\n", b"(dir_model).float()\n") and mel == MEL
    (repo, kw), = conversion.asked
    assert repo == models.FINETUNES["thai-pathumma"]["repo"]
    assert kw["revision"] == models.FINETUNES["thai-pathumma"]["revision"]


@pytest.mark.parametrize("bad", ["convert.py", "mel.npz"])
def test_a_file_with_the_wrong_checksum_means_nothing_is_run(conversion, bad):
    conversion.server.files[bad] += b"import os  # something else\n"
    with pytest.raises(SystemExit) as e:
        models.ensure("thai-pathumma")
    assert "checksum mismatch, nothing was run" in str(e.value) and not conversion.ran
    assert not models.path_for("thai-pathumma").exists()
    assert not [p for p in conversion.work.rglob("*") if p.is_file() and b"something else" in p.read_bytes()]


@pytest.mark.parametrize("gone", ["convert.py", "mel.npz"])
def test_a_file_that_is_not_there_means_nothing_is_run(conversion, gone):
    del conversion.server.files[gone]
    with pytest.raises(SystemExit, match="HTTP 404"):
        models.ensure("thai-pathumma")
    assert not conversion.ran


def test_what_an_older_babelscribe_left_is_not_run(conversion):
    """Older versions kept an unchecked converter from the master branch and a clone of openai/whisper."""
    conversion.work.mkdir(parents=True)
    (conversion.work / "convert-h5-to-ggml.py").write_text("raise SystemExit('old, unchecked')")
    (conversion.work / "convert-h5-to-ggml.orig.py").write_text("raise SystemExit('changed on disk')")
    stale = conversion.work / "openai-whisper" / "whisper" / "assets" / "mel_filters.npz"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"another table")
    models.ensure("thai-pathumma")
    (_, script, mel), = conversion.ran
    assert b"unchecked" not in script and b"changed on disk" not in script and mel == MEL
    assert [r for _, r in conversion.server.asked] == [None, None], "replaced, not continued onto the old bytes"


def test_checked_files_are_not_fetched_twice_and_a_cut_one_is_continued(conversion):
    conversion.server.plan = [("cut", 1000), "ok"]
    models.ensure("thai-pathumma")
    assert [r for _, r in conversion.server.asked] == [None, "bytes=1000-", None]
    models.path_for("thai-pathumma").unlink()
    models.ensure("thai-pathumma")
    assert len(conversion.server.asked) == 3 and len(conversion.ran) == 2


def test_a_stopped_quantizer_leaves_no_model(conversion, tmp_path):
    quantizer = tmp_path / "whisper-quantize"
    quantizer.write_bytes(b"x")
    with pytest.raises(KeyboardInterrupt):
        models.ensure("thai-pathumma", quantizer)
    assert not models.path_for("thai-pathumma").exists()


def test_every_download_that_can_run_code_names_one_commit():
    for url in (models.CONVERTER, models.MEL_FILTERS):
        assert re.search(r"/[0-9a-f]{40}/", url), url
    for name, ft in models.FINETUNES.items():
        assert re.fullmatch(r"[0-9a-f]{40}", ft["revision"]), name
    assert len(models.CONVERTER_SHA256) == len(models.MEL_FILTERS_SHA256) == 64


def fetched(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "babelscribe-tests"}),
                                    timeout=20) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) or e.code >= 500:
            pytest.skip(f"the server is busy: {e}")
        raise                                          # 404: a pin that does not exist must fail
    except OSError as e:
        pytest.skip(f"no network: {e}")


def test_the_pinned_converter_files_are_the_upstream_ones_and_the_patch_still_applies():
    script = fetched(models.CONVERTER)
    assert sha(script) == models.CONVERTER_SHA256 and script.count(models.LOADS.encode()) == 1
    assert sha(fetched(models.MEL_FILTERS)) == models.MEL_FILTERS_SHA256


@pytest.mark.parametrize("name", sorted(models.FINETUNES))
def test_the_pinned_fine_tune_commit_exists_and_has_what_the_converter_reads(name):
    ft = models.FINETUNES[name]
    info = json.loads(fetched(f"https://huggingface.co/api/models/{ft['repo']}/revision/{ft['revision']}"))
    files = {s["rfilename"] for s in info["siblings"]}
    assert info["sha"] == ft["revision"] and {"vocab.json", "added_tokens.json", "config.json"} <= files
