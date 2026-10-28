from pathlib import Path

from babelscribe import align, backend, writers


def test_asset_name_is_known_flavour():
    name = backend.asset_name()
    assert name.startswith("whisper-cli-") and name.endswith(".zip")


def test_pick_device_prefers_discrete():
    found = [{"backend": "vulkan", "id": 0, "name": "Intel UHD", "detail": "uma: 1"},
             {"backend": "vulkan", "id": 1, "name": "Radeon", "detail": "uma: 0"}]
    assert backend.pick_device(found) == 1


def test_hybrid_keeps_accurate_text_and_timing():
    timing = [{"start": 0.0, "end": 2.0, "text": "helo wrld", "words": [["helo", 0.0, 1.0], [" wrld", 1.0, 2.0]]},
              {"start": 2.0, "end": 4.0, "text": "how ar you", "words": [["how", 2.0, 2.6], [" ar", 2.6, 3.2], [" you", 3.2, 4.0]]}]
    text = [{"start": 0, "end": 4, "text": "hello world how are you", "words": []}]
    out = align.hybrid(text, timing)
    assert " ".join(s["text"] for s in out) == "hello world how are you"
    assert out[0]["start"] < 0.2 and out[-1]["end"] == 4.0
    assert [s["text"] for s in out] == ["hello world", "how are you"]   # cut on the timing model segment boundary


def test_hybrid_thai_no_spaces():
    timing = [{"start": 0.0, "end": 3.0, "text": "สวัสดีครับ", "words": [["สวัสดี", 0.0, 1.5], ["ครับ", 1.5, 3.0]]}]
    out = align.hybrid([{"start": 0, "end": 3, "text": "สวัสดีครับ", "words": []}], timing)
    assert out[0]["text"] == "สวัสดีครับ"


def test_writers(tmp_path: Path):
    segs = [{"start": 0.0, "end": 1.5, "text": "hi", "words": []}]
    files = writers.write(segs, tmp_path / "x", ["srt", "vtt", "txt", "json"], {})
    assert (tmp_path / "x.srt").read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> 00:00:01,500\nhi")
    assert len(files) == 4


def test_accurate_models_resolve():
    from babelscribe import cli, models  # noqa: F401  (import catches syntax errors in every module)
    for lang, name in models.ACCURATE.items():
        _, ft = models.resolve(name)
        assert ft and ft["lang"] == lang


def test_mcp_server_tools(tmp_path):
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import anyio, json
    from babelscribe import mcp_server
    srv = mcp_server.build()
    (tmp_path / "talk.mp4").write_bytes(b"x"); (tmp_path / "notes.txt").write_text("x")

    async def go():
        names = {t.name for t in await srv.list_tools()}
        assert {"transcribe", "find_media", "list_devices", "list_languages_and_models"} <= names
        return await srv.call_tool("find_media", {"folder": str(tmp_path)})
    out = anyio.run(go)
    assert "talk.mp4" in json.dumps(out, default=str) and "notes.txt" not in json.dumps(out, default=str)


def _argv_of(monkeypatch, tmp_path, runner, *args, **kw):
    """Run a whisper-cli caller with ffmpeg and subprocess mocked; return the argv it built."""
    import json, subprocess
    from babelscribe import transcribe
    seen = []

    def fake_run(cmd, *a, **k):
        seen.append(list(cmd))
        for i, c in enumerate(cmd):
            if c == "-of":
                Path(cmd[i + 1] + ".json").write_text(json.dumps({"transcription": []}), encoding="utf-8")
            if c == "-f":
                Path(cmd[i + 1] + ".json").write_text(json.dumps({"transcription": []}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(transcribe.subprocess, "run", fake_run)
    monkeypatch.setattr(transcribe, "to_wav16k", lambda *a, **k: None)
    runner(*args, **kw)
    return seen[-1]


def test_prompt_reaches_whisper_cli(monkeypatch, tmp_path):
    from babelscribe import transcribe
    text = "Pitakpong, babelscribe สวัสดี"
    argv = _argv_of(monkeypatch, tmp_path, transcribe.run, Path("whisper-cli"), Path("m.bin"), tmp_path / "a.wav", "en", 0, prompt=text)
    assert argv.count("--prompt") == 1 and argv[argv.index("--prompt") + 1] == text
    assert "-mc" not in argv   # whisper.cpp ignores the prompt with -mc 0


def test_no_prompt_keeps_argv(monkeypatch, tmp_path):
    from babelscribe import transcribe
    for p in (None, "", "   "):
        argv = _argv_of(monkeypatch, tmp_path, transcribe.run, Path("whisper-cli"), Path("m.bin"), tmp_path / "a.wav", "en", 0, prompt=p)
        assert "--prompt" not in argv
        assert argv[argv.index("-mc"):argv.index("-mc") + 2] == ["-mc", "0"]


def test_prompt_reaches_hybrid_pass(monkeypatch, tmp_path):
    from babelscribe import hybrid
    segs = [{"start": 0.0, "end": 2.0, "text": "x", "words": []}]
    argv = _argv_of(monkeypatch, tmp_path, hybrid.run, Path("whisper-cli"), Path("m.bin"), tmp_path / "a.wav", segs, "th", 0, None,
                    prompt="  Pitakpong  ")
    assert argv.count("--prompt") == 1 and argv[argv.index("--prompt") + 1] == "Pitakpong"
    argv = _argv_of(monkeypatch, tmp_path, hybrid.run, Path("whisper-cli"), Path("m.bin"), tmp_path / "a.wav", segs, "th", 0, None)
    assert "--prompt" not in argv and "-mc" in argv


def test_cli_prompt_flag_reaches_api(monkeypatch):
    from babelscribe import api, cli
    got = {}
    monkeypatch.setattr(api, "transcribe_file", lambda *a, **k: got.update(k))
    cli.main(["talk.mp4", "--prompt", "Pitakpong, babelscribe"])
    assert got["prompt"] == "Pitakpong, babelscribe"
    cli.main(["talk.mp4"])
    assert not got["prompt"]


def test_mcp_vocabulary_reaches_api(monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import api, mcp_server
    got = {}
    monkeypatch.setattr(api, "transcribe_file", lambda *a, **k: (got.update(k), {"text": ""})[1])
    srv = mcp_server.build()
    anyio.run(srv.call_tool, "transcribe", {"file_path": str(tmp_path / "t.mp4"), "vocabulary": "Pitakpong, babelscribe"})
    assert got["prompt"] == "Pitakpong, babelscribe"


def test_writers_wrap_long_subtitle_lines(tmp_path: Path):
    segs = [{
        "start": 0.0,
        "end": 4.0,
        "text": "This is a long subtitle line",
        "words": [
            ["This", 0.0, 0.4],
            [" is", 0.4, 0.7],
            [" a", 0.7, 0.9],
            [" long", 0.9, 1.3],
            [" subtitle", 1.3, 2.2],
            [" line", 2.2, 4.0],
        ],
    }]

    writers.write(
        segs,
        tmp_path / "wrapped",
        ["srt"],
        {},
        max_line_chars=20,
    )

    text = (tmp_path / "wrapped.srt").read_text(encoding="utf-8")

    assert "This is a long\nsubtitle line" in text
def test_writers_wrap_long_vtt_lines(tmp_path: Path):
    segs = [{
        "start": 0.0,
        "end": 4.0,
        "text": "This is a long subtitle line",
        "words": [
            ["This", 0.0, 0.4],
            [" is", 0.4, 0.7],
            [" a", 0.7, 0.9],
            [" long", 0.9, 1.3],
            [" subtitle", 1.3, 2.2],
            [" line", 2.2, 4.0],
        ],
    }]

    writers.write(
        segs,
        tmp_path / "wrapped",
        ["vtt"],
        {},
        max_line_chars=20,
    )

    text = (tmp_path / "wrapped.vtt").read_text(encoding="utf-8")

    assert text.startswith("WEBVTT\n\n")
    assert "This is a long\nsubtitle line" in text

def test_writers_use_smaller_default_for_thai(tmp_path: Path):
    thai_text = "สวัสดีครับวันนี้อากาศดีมากนะครับ"

    segs = [{
        "start": 0.0,
        "end": 3.0,
        "text": thai_text,
        "words": [
            ["สวัสดี", 0.0, 0.6],
            ["ครับ", 0.6, 0.9],
            ["วันนี้", 0.9, 1.4],
            ["อากาศ", 1.4, 1.9],
            ["ดีมาก", 1.9, 2.4],
            ["นะครับ", 2.4, 3.0],
        ],
    }]

    writers.write(
        segs,
        tmp_path / "thai",
        ["srt"],
        {"lang": "th"},
    )

    text = (tmp_path / "thai.srt").read_text(encoding="utf-8")
    blocks = [
        block for block in text.strip().split("\n\n")
        if block
    ]

    assert len(blocks) == 1

    subtitle_lines = blocks[0].splitlines()[2:]

    assert len(subtitle_lines) == 2
    assert all(0 < len(line) <= 24 for line in subtitle_lines)
    assert "".join(subtitle_lines) == thai_text


def test_writers_split_long_subtitles_into_multiple_cues(tmp_path: Path):
    segs = [{
        "start": 0.0,
        "end": 4.0,
        "text": "One two three four five six seven eight",
        "words": [
            ["One", 0.0, 0.3],
            [" two", 0.3, 0.6],
            [" three", 0.6, 1.0],
            [" four", 1.0, 1.3],
            [" five", 1.3, 1.6],
            [" six", 1.6, 1.9],
            [" seven", 1.9, 2.3],
            [" eight", 2.3, 2.7],
        ],
    }]

    writers.write(
        segs,
        tmp_path / "multi",
        ["srt"],
        {},
        max_line_chars=10,
    )

    text = (tmp_path / "multi.srt").read_text(encoding="utf-8")
    blocks = [block for block in text.strip().split("\n\n") if block]

    # Every SRT block is a subtitle cue.
    cues = blocks

    assert len(cues) == 3

    for cue in cues:
        # Skip the cue number and timestamp.
        subtitle_lines = cue.splitlines()[2:]
        assert len(subtitle_lines) <= 2

    subtitle_text = " ".join(
        line
        for cue in cues
        for line in cue.splitlines()[2:]
    )

    assert subtitle_text == "One two three four five six seven eight"


def test_translate_adds_tr_flag(monkeypatch, tmp_path):
    from babelscribe import transcribe
    argv = _argv_of(monkeypatch, tmp_path, transcribe.run, Path("whisper-cli"), Path("m.bin"), tmp_path / "a.wav", "th", 0, translate=True)
    assert "-tr" in argv
    argv = _argv_of(monkeypatch, tmp_path, transcribe.run, Path("whisper-cli"), Path("m.bin"), tmp_path / "a.wav", "th", 0)
    assert "-tr" not in argv


def test_translate_rejects_text_model_and_swaps_turbo(monkeypatch, tmp_path):
    import pytest
    from babelscribe import api
    media = tmp_path / "t.wav"
    media.write_bytes(b"x")
    with pytest.raises(ValueError):
        api.transcribe_file(media, "th", text_model="thai-thonburian", translate=True)
    seen = {}

    def fake_setup(model, *a, **k):
        seen["model"] = model
        raise RuntimeError("stop")
    monkeypatch.setattr(api, "setup", fake_setup)
    with pytest.raises(RuntimeError):
        api.transcribe_file(media, "th", translate=True, log=lambda m: None)
    assert seen["model"] == "large-v3"


def test_cli_translate_flag_reaches_api(monkeypatch):
    from babelscribe import api, cli
    got = {}
    monkeypatch.setattr(api, "transcribe_file", lambda *a, **k: got.update(k))
    cli.main(["talk.mp4", "--translate"])
    assert got["translate"] is True
    cli.main(["talk.mp4"])
    assert got["translate"] is False


def test_mcp_translate_reaches_api(monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import api, mcp_server
    got = {}
    monkeypatch.setattr(api, "transcribe_file", lambda *a, **k: (got.update(k), {"text": ""})[1])
    srv = mcp_server.build()
    anyio.run(srv.call_tool, "transcribe", {"file_path": str(tmp_path / "t.mp4"), "translate": True})
    assert got["translate"] is True
