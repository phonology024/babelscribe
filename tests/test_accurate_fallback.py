"""Accurate mode where the language's fine-tune cannot be had (no converter, as in the desktop app, and nothing
converted earlier): large-v3 does the work and one line says so, everywhere the person or their AI app can see it.
And only the files the converter reads are downloaded."""
import json
import sys
import types

import pytest

from babelscribe import api, cli, hybrid, models, ram, transcribe

LINE = ("the Thai fine-tune needs a one-time conversion that this install can't do; using large-v3, which is less "
        "accurate for Thai")


@pytest.fixture
def run(monkeypatch, tmp_path):
    """transcribe_file with stand-ins for the programs. converter=False: torch and the others are not installed."""
    monkeypatch.setattr(ram, "detect", lambda: None)
    monkeypatch.setattr(api, "_told", set())
    monkeypatch.setattr(models, "MODELS", tmp_path / "models")
    monkeypatch.delattr(sys, "frozen", raising=False)

    def go(converter=False, converted=(), lang="th", detected=None, **kw):
        seen = types.SimpleNamespace(ensured=[], beam=None, text_model=None, said=[])
        monkeypatch.setattr(models, "can_convert", lambda load=False: converter)
        (tmp_path / "models").mkdir(exist_ok=True)
        for name in converted:
            models.path_for(name).write_bytes(b"converted earlier")
        monkeypatch.setattr(api, "setup", lambda model, *a, **k: (
            tmp_path / "whisper-cli", tmp_path / f"{model}.bin", [{"id": 0, "backend": "cpu", "name": "CPU"}]))
        monkeypatch.setattr(models, "ensure", lambda name, *a, **k: seen.ensured.append(name) or tmp_path / name)
        monkeypatch.setattr(transcribe, "detected_language", lambda *a, **k: detected)

        def timing(binary, model, src, lang, dev, beam=None, **k):
            seen.beam = beam
            return [{"start": 0.0, "end": 1.0, "text": "x", "words": []}]

        def text_pass(binary, model, src, segs, *a, **k):
            seen.text_model = model.name
            return segs
        monkeypatch.setattr(transcribe, "run", timing)
        monkeypatch.setattr(hybrid, "run", text_pass)
        (tmp_path / "a.wav").write_bytes(b"x")
        seen.result = api.transcribe_file(tmp_path / "a.wav", lang=lang, formats=["srt", "json"], log=seen.said.append, **kw)
        seen.meta = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["meta"]
        return seen
    return go


def test_without_the_converter_thai_uses_large_v3_with_beam_5_and_says_so_once(run):
    r = run(accurate=True)
    assert r.ensured == ["large-v3"] and r.beam == 5 and r.text_model is None
    assert r.result["model"] == "large-v3" == r.meta["model"] and "text_model" not in r.meta
    note = r.result["accurate_note"]
    assert note.startswith(LINE) and 'pip install "babelscribe[finetune]"' in note
    assert r.said.count(note) == 1


def test_a_packaged_program_does_not_suggest_pip(run, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert run(accurate=True).result["accurate_note"] == LINE


def test_hindi_is_called_hindi(run):
    note = run(accurate=True, lang="hi").result["accurate_note"]
    assert "the Hindi fine-tune" in note and "less accurate for Hindi" in note
    assert set(models.ACCURATE) <= set(models.LANGUAGE_NAMES)


def test_a_detected_language_falls_back_the_same_way(run):
    r = run(accurate=True, lang="auto", detected="th")
    assert r.result["accurate_note"].startswith(LINE) and r.ensured == ["large-v3"]


@pytest.mark.parametrize("how", [dict(converted=["thai-pathumma"]), dict(converter=True)], ids=["converted-earlier", "can-convert"])
def test_a_converted_model_or_a_converter_means_the_fine_tune_as_before(run, how):
    r = run(accurate=True, **how)
    assert r.ensured == ["thai-pathumma"] and r.text_model == "thai-pathumma" and r.beam is None
    assert "accurate_note" not in r.result and r.meta["text_model"] == "thai-pathumma"
    assert not any("conversion" in s for s in r.said)


@pytest.mark.parametrize("model,used,beam", [("small", "small", None), ("large-v3", "large-v3", 5),
                                             ("large", "large-v3", 5)])
def test_a_model_named_by_hand_is_kept_and_the_line_names_it(run, model, used, beam):
    r = run(accurate=True, model=model)
    assert r.result["model"] == model and r.beam == beam and r.ensured == []
    assert f"using {used}," in r.result["accurate_note"]


@pytest.mark.parametrize("kw", [dict(lang="ja", accurate=True), dict(accurate=False), dict(accurate=True, translate=True)],
                         ids=["language-without-fine-tune", "not-accurate", "translate"])
def test_nothing_else_changes_or_says_anything(run, kw):
    r = run(**kw)
    assert "accurate_note" not in r.result and not any("conversion" in s for s in r.said)


def test_a_text_model_named_by_hand_is_still_an_error_without_the_converter(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "MODELS", tmp_path)
    monkeypatch.setitem(sys.modules, "torch", None)             # as in the packaged engine
    with pytest.raises(SystemExit, match=r"needs extras.*babelscribe\[finetune\]"):
        models.ensure("thai-pathumma")


@pytest.mark.parametrize("broken", [ImportError("DLL load failed"), OSError("cannot load libtorch")], ids=["import", "library"])
def test_a_converter_that_is_there_but_cannot_be_loaded_counts_as_missing(monkeypatch, broken):
    monkeypatch.setattr(models.importlib.util, "find_spec", lambda name: object())

    def fail(name):
        raise broken
    monkeypatch.setattr(models.importlib, "import_module", fail)
    assert models.can_convert() is True and models.can_convert(load=True) is False


@pytest.mark.parametrize("missing", ["torch", "transformers", "huggingface_hub", "numpy"])
def test_every_package_of_the_converter_is_needed(monkeypatch, missing):
    monkeypatch.setattr(models.importlib.util, "find_spec", lambda name: None if name == missing else object())
    assert models.can_convert() is False


def test_the_packaged_engine_counts_as_unable_to_convert():
    """Its spec leaves these out, so can_convert() is False there."""
    spec = (models.Path(__file__).parent.parent / "packaging" / "standalone" / "babelscribe.spec").read_text(encoding="utf-8")
    excluded = spec.split("excludes = [", 1)[1].split("]", 1)[0]
    assert all(f'"{name}"' in excluded for name in ("torch", "transformers", "numpy", "huggingface_hub"))


def test_the_batch_summary_carries_the_note(run, monkeypatch, tmp_path):
    run(accurate=True)                                              # sets the stand-ins up
    done = api.transcribe_many([tmp_path / "a.wav"], accurate=True, lang="th", formats=["srt"], log=lambda s: None)
    assert done["files"][0]["accurate_note"].startswith(LINE)


def test_the_desktop_app_gets_the_note_in_the_done_event(run, tmp_path, capsys):
    run(accurate=True)
    capsys.readouterr()
    cli.main([str(tmp_path / "a.wav"), "-l", "th", "--accurate", "--progress-json"])
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    done = next(e for e in events if e["event"] == "done")
    assert done["accurate_note"].startswith(LINE)
    assert sum(e["event"] == "log" and e["message"] == done["accurate_note"] for e in events) <= 1


@pytest.mark.parametrize("converter", [False, True])
def test_models_json_says_what_accurate_mode_will_use_here(monkeypatch, tmp_path, converter):
    monkeypatch.setattr(models, "MODELS", tmp_path)
    monkeypatch.setattr(models, "can_convert", lambda load=False: converter)
    r = ram.report(None)
    if converter:
        assert r["accurate"] == {**models.ACCURATE, "*": "large-v3"} and r["accurate_note"] == {}
    else:
        assert r["accurate"] == {"th": "large-v3", "hi": "large-v3", "*": "large-v3"} and set(r["accurate_note"]) == {"th", "hi"}
        models.path_for("hindi-vasista").write_bytes(b"x")
        r = ram.report(None)
        assert r["accurate"]["hi"] == "hindi-vasista" and set(r["accurate_note"]) == {"th"}


def test_an_ai_app_is_told_over_mcp(run, monkeypatch, tmp_path):
    pytest.importorskip("mcp.server.mcpserver")
    import anyio

    from babelscribe import mcp_server
    run(accurate=True)
    srv = mcp_server.build()

    def call(tool, args):
        return json.dumps(anyio.run(srv.call_tool, tool, args), default=lambda o: getattr(o, "__dict__", str(o)),
                          ensure_ascii=False)
    assert LINE in call("transcribe", {"file_path": str(tmp_path / "a.wav"), "language": "th", "accurate": True})
    assert LINE in call("transcribe_folder", {"folder": str(tmp_path), "language": "th", "accurate": True})
    listed = call("list_languages_and_models", {})
    assert LINE in listed and "thai-pathumma" not in listed.split("accurate_per_language", 1)[1].split("}", 1)[0]


# ------------------------------------------------------------------------------------------------- only what is read

def test_only_the_files_the_converter_reads_are_downloaded(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "MODELS", tmp_path)
    asked = []

    class Stop(Exception):
        pass

    def snapshot(repo, **kw):
        asked.append((repo, kw))
        raise Stop
    hub = types.ModuleType("huggingface_hub")
    hub.snapshot_download = snapshot
    for name, module in (("torch", types.ModuleType("torch")), ("transformers", types.ModuleType("transformers")),
                         ("huggingface_hub", hub)):
        monkeypatch.setitem(sys.modules, name, module)
    for name, ft in models.FINETUNES.items():
        with pytest.raises(Stop):
            models.ensure(name)
        repo, kw = asked[-1]
        assert repo == ft["repo"] and sorted(kw["allow_patterns"]) == sorted([*models.CONVERTER_READS, ft["weights"]])
        assert sum(p.endswith((".safetensors", ".bin", ".msgpack", ".h5", ".ckpt")) for p in kw["allow_patterns"]) == 1
        assert not any(c in p for p in kw["allow_patterns"] for c in "*?["), "exact names: nothing else slips in"
