from pathlib import Path

from babelscribe import align, backend, writers


def test_asset_name_is_known_flavour(monkeypatch):
    # Only assert the shape on a platform that actually has a build; see the next test for the rest.
    for system, arch in (("Windows", "AMD64"), ("Linux", "x86_64"), ("Darwin", "arm64")):
        monkeypatch.setattr(backend.platform, "system", lambda s=system: s)
        monkeypatch.setattr(backend.platform, "machine", lambda a=arch: a)
        name = backend.asset_name()
        assert name.startswith("whisper-cli-") and name.endswith(".zip")


def test_asset_name_refuses_a_platform_that_was_never_built(monkeypatch):
    """Linux arm64 and Intel macOS got a bare HTTP 404 from a name nothing was published under."""
    import pytest
    monkeypatch.setattr(backend.platform, "system", lambda: "Linux")
    monkeypatch.setattr(backend.platform, "machine", lambda: "aarch64")
    with pytest.raises(SystemExit) as e:
        backend.asset_name("cpu")
    msg = str(e.value)
    assert "no prebuilt whisper-cli for linux-arm64-cpu" in msg
    assert "--bin" in msg, "say how to work around it, not just that it failed"


def test_asset_name_matches_the_assets_the_release_actually_publishes(monkeypatch):
    """The names must stay in step with .github/workflows/build-binaries.yml."""
    published = {"whisper-cli-linux-x64-cpu.zip", "whisper-cli-linux-x64-cuda.zip",
                 "whisper-cli-linux-x64-vulkan.zip", "whisper-cli-macos-arm64-metal.zip",
                 "whisper-cli-windows-x64-cpu.zip", "whisper-cli-windows-x64-vulkan.zip"}
    made = set()
    for system, machines in (("Windows", ["AMD64"]), ("Linux", ["x86_64"]), ("Darwin", ["arm64"])):
        for machine in machines:
            monkeypatch.setattr(backend.platform, "system", lambda s=system: s)
            monkeypatch.setattr(backend.platform, "machine", lambda m=machine: m)
            for flavor in ("cpu", "vulkan", "cuda", "metal"):
                try:
                    made.add(backend.asset_name(flavor))
                except SystemExit:
                    pass
    assert made == published


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


def _tool_payload(result):
    """call_tool returns a CallToolResult; the tool's dict is the JSON in its first text block."""
    import json
    return json.loads(result.content[0].text)


def test_mcp_transcribe_folder_batches_every_media_file(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import anyio, json
    from babelscribe import api, mcp_server

    calls = []

    def fake_transcribe(src, *a, **k):
        calls.append((Path(src).name, k.get("out")))
        return {"files": [str(Path(src).with_suffix(".srt"))], "lang": "en", "segments": 1, "seconds": 0.1, "text": "hi"}
    monkeypatch.setattr(api, "transcribe_file", fake_transcribe)

    sub = tmp_path / "nested"
    sub.mkdir()
    for name in ("a.mp4", "b.mp3", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    (sub / "c.mov").write_bytes(b"x")

    srv = mcp_server.build()

    async def go(**kwargs):
        return await srv.call_tool("transcribe_folder", {"folder": str(tmp_path), "formats": "srt", **kwargs})
    out = _tool_payload(anyio.run(go))

    assert "transcribe_folder" in {t.name for t in anyio.run(srv.list_tools)}
    assert sorted(c[0] for c in calls) == ["a.mp4", "b.mp3"], "non-media and sub-folders are skipped by default"
    assert (out["total"], out["succeeded"], out["failed"]) == (2, 2, 0)
    assert all(f["ok"] for f in out["files"])


def test_mcp_transcribe_folder_recursive_and_continues_after_failure(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import anyio, json
    from babelscribe import api, mcp_server

    seen = []

    def fake_transcribe(src, *a, **k):
        seen.append(Path(src).name)
        if Path(src).name == "bad.mp4":
            raise RuntimeError("whisper-cli failed (1)")
        return {"files": [], "lang": "en", "segments": 1, "seconds": 0.1, "text": "hi"}
    monkeypatch.setattr(api, "transcribe_file", fake_transcribe)

    sub = tmp_path / "nested"
    sub.mkdir()
    (tmp_path / "bad.mp4").write_bytes(b"x")
    (sub / "good.mp3").write_bytes(b"x")

    srv = mcp_server.build()

    async def go():
        return await srv.call_tool("transcribe_folder", {"folder": str(tmp_path), "recursive": True})
    out = _tool_payload(anyio.run(go))

    assert sorted(seen) == ["bad.mp4", "good.mp3"], "a failing file must not stop the batch"
    assert (out["total"], out["succeeded"], out["failed"]) == (2, 1, 1)
    failed = next(f for f in out["files"] if not f["ok"])
    assert "whisper-cli failed" in failed["error"]


def test_mcp_transcribe_folder_rejects_a_file(tmp_path):
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import mcp_server

    target = tmp_path / "one.mp4"
    target.write_bytes(b"x")
    srv = mcp_server.build()

    async def go():
        return await srv.call_tool("transcribe_folder", {"folder": str(target)})
    with pytest.raises(Exception) as exc:
        anyio.run(go)
    assert "not a folder" in str(exc.value.__cause__)


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

def test_writers_keep_dots_in_the_input_name(tmp_path: Path):
    # api.transcribe_file passes src.with_suffix("") as the base, so "meeting.v2.mp4" -> "meeting.v2".
    # Appending (not replacing) the extension keeps "meeting.v2.srt" instead of collapsing to "meeting.srt".
    segs = [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}]

    files = writers.write(segs, tmp_path / "meeting.v2", ["srt", "vtt", "txt", "json"], {})

    assert sorted(f.name for f in files) == [
        "meeting.v2.json",
        "meeting.v2.srt",
        "meeting.v2.txt",
        "meeting.v2.vtt",
    ]
    assert all(f.exists() for f in files)


def test_writers_do_not_collide_on_dotted_names(tmp_path: Path):
    # Two recordings of the same meeting must not overwrite each other's subtitles.
    first = writers.write([{"start": 0.0, "end": 1.0, "text": "first", "words": []}], tmp_path / "meeting.v1", ["srt"], {})
    second = writers.write([{"start": 0.0, "end": 1.0, "text": "second", "words": []}], tmp_path / "meeting.v2", ["srt"], {})

    assert first[0] != second[0]
    assert "first" in first[0].read_text(encoding="utf-8")
    assert "second" in second[0].read_text(encoding="utf-8")


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


def test_out_into_missing_folder_is_created(monkeypatch, tmp_path):
    """-o into a folder that does not exist used to fail at the very end with a bare errno, after the whole run."""
    from babelscribe import api, transcribe
    media = tmp_path / "t.wav"
    media.write_bytes(b"x")
    monkeypatch.setattr(api, "setup", lambda *a, **k: (Path("whisper-cli"), Path("m.bin"), [{"backend": "cpu", "id": 0, "name": "CPU"}]))
    monkeypatch.setattr(api.transcribe, "run", lambda *a, **k: [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}])
    res = api.transcribe_file(media, lang="en", out=tmp_path / "new" / "deep" / "talk", log=lambda m: None)
    assert (tmp_path / "new" / "deep" / "talk.srt").is_file()
    assert res["segments"] == 1


def test_out_dir_is_created_before_the_slow_work(monkeypatch, tmp_path):
    """A bad -o must fail before the model download and inference, not after them."""
    import pytest
    from babelscribe import api
    media = tmp_path / "t.wav"
    media.write_bytes(b"x")
    called = []
    monkeypatch.setattr(api, "setup", lambda *a, **k: called.append("setup"))
    # A file where a folder is needed: mkdir must raise before setup runs.
    blocked = tmp_path / "blocked"
    blocked.write_text("x")
    with pytest.raises((FileExistsError, NotADirectoryError, OSError)):
        api.transcribe_file(media, lang="en", out=blocked / "sub" / "talk", log=lambda m: None)
    assert called == []


def _ass_events(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    head = lines[:lines.index("[Events]")]
    events = [ln for ln in lines if ln.startswith("Dialogue:")]
    return "\n".join(head), events


def test_ass_output_has_a_valid_header_and_one_event_per_cue(tmp_path: Path):
    segs = [{"start": 0.0, "end": 2.0, "text": "Hello there world",
             "words": [["Hello", 0.0, 0.5], [" there", 0.5, 1.0], [" world", 1.0, 2.0]]}]

    (path,) = writers.write(segs, tmp_path / "k", ["ass"], {"lang": "en"})
    head, events = _ass_events(path)

    assert head.startswith("[Script Info]")
    assert "[V4+ Styles]" in head and "Style: Default," in head
    assert "PlayResX: 1920" in head
    assert len(events) == 1
    assert events[0].endswith("{\\k50}Hello{\\k50} there{\\k100} world")


def test_ass_karaoke_tags_follow_word_timings(tmp_path: Path):
    # A gap between "alpha" and "beta": the highlight must hold on alpha until beta starts, not run ahead.
    segs = [{"start": 0.0, "end": 3.0, "text": "alpha beta",
             "words": [["alpha", 0.0, 1.0], [" beta", 2.0, 3.0]]}]

    (path,) = writers.write(segs, tmp_path / "gap", ["ass"], {"lang": "en"})
    _, (event,) = _ass_events(path)

    assert "{\\k200}alpha" in event, "alpha holds until beta starts at 2.0 s"
    assert "{\\k100} beta" in event, "beta runs from 2.0 s to the cue end at 3.0 s"


def test_ass_escapes_braces_so_they_cannot_swallow_the_line(tmp_path: Path):
    segs = [{"start": 0.0, "end": 1.0, "text": "use {\\b1}bold", "words": []}]

    (path,) = writers.write(segs, tmp_path / "braces", ["ass"], {"lang": "en"})
    _, (event,) = _ass_events(path)

    assert "{\\b1}" not in event, "a literal override tag from the transcript must not reach libass"
    assert "｛" in event and "｝" in event


def test_ass_without_word_timings_is_plain_and_unspoken_coloured(tmp_path: Path):
    segs = [{"start": 0.0, "end": 1.0, "text": "no timing", "words": []}]

    (path,) = writers.write(segs, tmp_path / "plain", ["ass"], {"lang": "en"})
    _, (event,) = _ass_events(path)

    assert "\\k" not in event, "never invent word timings"
    assert event.endswith("{\\c&H00FFFFFF}no timing"), "no \\k means PrimaryColour (spoken); pin it to unspoken"


def test_ass_splits_at_its_own_shorter_limit_not_the_subtitle_one(tmp_path: Path):
    # 34 characters: fits one 34-char subtitle line under the 42 limit, but ASS splits at 32 because
    # karaoke is read word by word.
    words = [[w, i * 0.1, i * 0.1 + 0.1] for i, w in enumerate(["aaaa", " bbbb", " cccc", " dddd", " eeee", " ffff", " gggg"])]
    segs = [{"start": 0.0, "end": 0.7, "text": "aaaa bbbb cccc dddd eeee ffff gggg", "words": words}]

    (ass_path,) = writers.write(segs, tmp_path / "k", ["ass"], {"lang": "en"})
    (srt_path,) = writers.write(segs, tmp_path / "k", ["srt"], {"lang": "en"})
    _, events = _ass_events(ass_path)

    srt_text = srt_path.read_text(encoding="utf-8")
    assert "\n" not in srt_text.split("\n\n")[0].splitlines()[2], "SRT keeps the whole 34-char line on one line"
    assert len(events) == 1 and "\\N" in events[0], "ASS wraps it at 32 characters into two lines"
    for event in events:
        assert event.count("\\N") <= 1, "an ASS event holds at most two rendered lines"


def test_ass_mixes_with_the_other_formats(tmp_path: Path):
    segs = [{"start": 0.0, "end": 1.0, "text": "hi", "words": [["hi", 0.0, 1.0]]}]

    files = writers.write(segs, tmp_path / "all", ["srt", "ass", "json"], {"lang": "en"})

    assert [f.suffix for f in files] == [".srt", ".ass", ".json"]
    assert all(f.exists() for f in files)


def _transcribe_with_device(monkeypatch, tmp_path, device):
    """Run transcribe_file with setup/model work stubbed out, so only device handling is exercised."""
    import pytest
    from babelscribe import api
    media = tmp_path / "d.wav"
    media.write_bytes(b"x")
    found = [{"backend": "metal", "id": 0, "name": "Apple M4 Pro", "detail": "uma: 1"},
             {"backend": "cpu", "id": 1, "name": "CPU", "detail": ""}]
    monkeypatch.setattr(api, "setup", lambda *a, **k: (Path("whisper-cli"), Path("m.bin"), found))
    monkeypatch.setattr(api.transcribe, "run", lambda *a, **k: [])
    return api.transcribe_file(media, "en", device=device, log=lambda m: None, formats=["txt"])


def test_device_rejects_a_non_number(monkeypatch, tmp_path):
    import pytest
    with pytest.raises(ValueError) as e:
        _transcribe_with_device(monkeypatch, tmp_path, "foo")
    assert "device must be" in str(e.value), "not a bare int() ValueError from deep inside"


def test_device_rejects_an_id_the_driver_does_not_have(monkeypatch, tmp_path):
    import pytest
    for bad in (5, -1, "2"):
        with pytest.raises(ValueError) as e:
            _transcribe_with_device(monkeypatch, tmp_path, bad)
        assert "no device" in str(e.value) and "Apple M4 Pro" in str(e.value), "list the ids that do exist"


def test_device_accepts_auto_none_and_a_listed_id(monkeypatch, tmp_path):
    assert _transcribe_with_device(monkeypatch, tmp_path, "auto")["device"].startswith("metal")
    assert _transcribe_with_device(monkeypatch, tmp_path, None)["device"].startswith("metal")
    assert _transcribe_with_device(monkeypatch, tmp_path, "1")["device"].startswith("cpu")
    assert _transcribe_with_device(monkeypatch, tmp_path, 1)["device"].startswith("cpu")


def test_asset_name_leaves_a_self_hosted_mirror_alone(monkeypatch):
    """README: 'Point BABELSCRIBE_RELEASES at another URL to self-host'. A mirror can carry builds the project
    does not publish (linux-arm64 is the likely one), so the table of published assets must not veto it."""
    monkeypatch.setattr(backend, "RELEASES", "https://example.invalid/mirror")
    monkeypatch.setattr(backend.platform, "system", lambda: "Linux")
    monkeypatch.setattr(backend.platform, "machine", lambda: "aarch64")
    assert backend.asset_name("cpu") == "whisper-cli-linux-arm64-cpu.zip"


def test_fetch_binary_explains_a_404_from_a_mirror(monkeypatch, tmp_path):
    import urllib.error
    import pytest
    monkeypatch.setattr(backend, "RELEASES", "https://example.invalid/mirror")
    monkeypatch.setattr(backend, "CACHE", tmp_path)

    def gone(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
    monkeypatch.setattr(backend.urllib.request, "urlopen", gone)
    with pytest.raises(SystemExit) as e:
        backend.fetch_binary("cpu")
    assert "404" in str(e.value) and "--bin" in str(e.value)


def test_mcp_tool_error_instead_of_exit_on_an_unsupported_platform(monkeypatch, tmp_path):
    """The CLI reports 'no prebuilt whisper-cli' with SystemExit, raised in a worker thread under the MCP server.
    The client must get a tool error with that text; the server must keep running."""
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import api, mcp_server

    def unsupported(*a, **k):
        raise SystemExit("no prebuilt whisper-cli for linux-arm64-cpu; available: ...")
    monkeypatch.setattr(api, "transcribe_file", unsupported)
    monkeypatch.setattr(api, "setup", unsupported)
    srv = mcp_server.build()
    for tool, args in (("transcribe", {"file_path": str(tmp_path / "a.wav")}), ("list_devices", {})):
        with pytest.raises(Exception) as e:      # Exception, not BaseException: SystemExit would not be caught here
            anyio.run(srv.call_tool, tool, args)
        assert "no prebuilt whisper-cli for linux-arm64-cpu" in str(e.value)
    assert anyio.run(srv.call_tool, "list_languages_and_models", {})   # still answering


def test_mcp_server_module_imports_without_the_sdk_types():
    """`babelscribe mcp` on Python 3.9 must reach its "needs Python 3.10+" message, so importing the module
    cannot evaluate 3.10-only syntax such as `float | None` at module level. CI runs this on 3.9."""
    import importlib
    from babelscribe import mcp_server
    importlib.reload(mcp_server)


def _folder_run(tmp_path, monkeypatch, names, fake=None, **kwargs):
    """Call transcribe_folder on real files with a transcribe_file stub that still writes through writers.write,
    so output-path mistakes show up on disk instead of being hidden by a mock."""
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import api, mcp_server

    def write_like_the_real_one(src, *a, out=None, formats=None, log=print, **k):
        base = Path(out) if out else Path(src).with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        segs = [{"start": 0.0, "end": 1.0, "text": Path(src).name, "words": []}]
        files = writers.write(segs, base, formats, {"language": "en"})
        return {"files": [str(f) for f in files], "lang": "en", "segments": 1, "seconds": 0.0, "text": ""}
    monkeypatch.setattr(api, "transcribe_file", fake or write_like_the_real_one)
    for n in names:
        (tmp_path / "in" / n).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "in" / n).write_bytes(b"x")
    srv = mcp_server.build()
    return _tool_payload(anyio.run(lambda: srv.call_tool(
        "transcribe_folder", {"folder": str(tmp_path / "in"), "formats": "srt", **kwargs})))


def test_mcp_transcribe_folder_never_writes_two_files_to_one_path(tmp_path, monkeypatch):
    """a/talk.mp4, a/talk.mp3 and b/talk.mp4 used to report succeeded: 3 and leave one talk.srt on disk."""
    names = ["a/talk.mp4", "a/talk.mp3", "b/talk.mp4", "b/other.wav"]
    for kwargs in ({"recursive": True}, {"recursive": True, "output_dir": str(tmp_path / "out")}):
        out = _folder_run(tmp_path, monkeypatch, names, **kwargs)
        written = [f for r in out["files"] for f in r["files"]]
        assert out["succeeded"] == 4 and len(set(written)) == 4
        for f in written:   # each subtitle holds its own source's text, so nothing was overwritten
            assert Path(f).is_file()
        texts = sorted(Path(f).read_text(encoding="utf-8").splitlines()[2] for f in written)
        assert texts == ["other.wav", "talk.mp3", "talk.mp4", "talk.mp4"]
        root = tmp_path / ("out" if "output_dir" in kwargs else "in")
        assert sorted(str(Path(f).relative_to(root)).replace("\\", "/") for f in written) == [
            "a/talk.mp3.srt", "a/talk.mp4.srt", "b/other.srt", "b/talk.srt"]


def test_mcp_transcribe_folder_survives_systemexit_in_one_file(tmp_path, monkeypatch):
    """writers.write and models.resolve raise SystemExit, which `except Exception` does not catch."""
    def fake(src, *a, **k):
        if Path(src).name == "bad.mp4":
            raise SystemExit("unknown format: docx")
        return {"files": [], "lang": "en", "segments": 1, "seconds": 0.0, "text": ""}
    out = _folder_run(tmp_path, monkeypatch, ["bad.mp4", "good.mp4"], fake=fake)
    assert (out["succeeded"], out["failed"]) == (1, 1)
    assert "unknown format: docx" in next(f for f in out["files"] if not f["ok"])["error"]


def test_mcp_progress_keeps_coming_during_one_long_file(tmp_path, monkeypatch):
    """A client times out when nothing arrives for a while, so a folder with one long file needs the same
    heartbeat `transcribe` has, not only a notification between files."""
    import pytest
    pytest.importorskip("mcp.server.mcpserver")
    import time
    from babelscribe import mcp_server
    monkeypatch.setattr(mcp_server, "HEARTBEAT", 0.05)
    sent = []

    async def record(ctx, progress, total, message):
        sent.append((progress, total, message))
    monkeypatch.setattr(mcp_server, "_report_progress", record)

    def slow(src, *a, log=print, **k):
        log("transcribing with turbo ...")
        time.sleep(0.4)
        return {"files": [], "lang": "en", "segments": 1, "seconds": 0.4, "text": ""}
    out = _folder_run(tmp_path, monkeypatch, ["long.mp4"], fake=slow)
    assert out["succeeded"] == 1
    during = [m for p, t, m in sent if m.startswith("long.mp4 (1/1): ")]
    assert len(during) >= 2, sent
    assert during[-1] == "long.mp4 (1/1): transcribing with turbo ..."
    assert all(t == 1 for _, t, _ in sent), "progress stays on the file-count scale so a client can show a bar"


def _batch(tmp_path, monkeypatch, names, argv, bad=()):
    """Run the CLI on real files with a transcribe_file stub that still writes through writers.write, so a wrong
    output path shows up on disk. Returns (exit code, files handed to transcribe_file in order)."""
    from babelscribe import api, cli
    called = []

    def fake(src, formats=None, out=None, log=print, **k):
        called.append(Path(src).name)
        if Path(src).name in bad:
            raise RuntimeError("whisper-cli failed")
        base = Path(out) if out else Path(src).with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        segs = [{"start": 0.0, "end": 1.0, "text": Path(src).name, "words": []}]
        files = writers.write(segs, base, formats, {"lang": "en"})
        return {"files": [str(f) for f in files], "lang": "en", "segments": 1, "seconds": 0.0, "text": ""}
    monkeypatch.setattr(api, "transcribe_file", fake)
    for n in names:
        (tmp_path / n).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / n).write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    try:
        cli.main(argv)
    except SystemExit as e:
        return e.code, called
    return 0, called


def test_cli_takes_several_files(tmp_path, monkeypatch, capsys):
    code, called = _batch(tmp_path, monkeypatch, ["a.mp4", "b.mp3"], ["a.mp4", "b.mp3", "-f", "srt"])
    assert code == 0 and called == ["a.mp4", "b.mp3"]
    assert (tmp_path / "a.srt").is_file() and (tmp_path / "b.srt").is_file()
    assert "2 done, 0 skipped, 0 failed" in capsys.readouterr().out


def test_cli_takes_a_folder_and_only_goes_deeper_with_r(tmp_path, monkeypatch):
    names = ["rec/a.mp4", "rec/notes.txt", "rec/sub/b.wav"]
    code, called = _batch(tmp_path, monkeypatch, names, ["rec", "-f", "srt"])
    assert code == 0 and called == ["a.mp4"]            # notes.txt is not media, sub/ needs -r
    code, called = _batch(tmp_path, monkeypatch, names, ["rec", "-r", "-f", "srt", "-o", "subs"])
    assert code == 0 and called == ["a.mp4", "b.wav"]
    assert (tmp_path / "subs" / "a.srt").is_file() and (tmp_path / "subs" / "sub" / "b.srt").is_file()


def test_cli_skip_existing_leaves_finished_files(tmp_path, monkeypatch, capsys):
    names = ["rec/a.mp4", "rec/b.mp4"]
    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "a.srt").write_text("mine", encoding="utf-8")
    code, called = _batch(tmp_path, monkeypatch, names, ["rec", "-f", "srt", "--skip-existing"])
    assert code == 0 and called == ["b.mp4"]
    assert (tmp_path / "rec" / "a.srt").read_text(encoding="utf-8") == "mine"
    assert "1 done, 1 skipped, 0 failed" in capsys.readouterr().out
    # every requested format must be there: a.srt alone does not make a.mp4 done for srt + json
    code, called = _batch(tmp_path, monkeypatch, names, ["rec", "-f", "srt,json", "--skip-existing"])
    assert "a.mp4" in called


def test_cli_one_failing_file_in_the_middle_does_not_stop_the_rest(tmp_path, monkeypatch, capsys):
    code, called = _batch(tmp_path, monkeypatch, ["a.mp4", "b.mp4", "c.mp4"], ["a.mp4", "b.mp4", "c.mp4", "-f", "srt"],
                          bad={"b.mp4"})
    out = capsys.readouterr().out
    assert code == 1 and called == ["a.mp4", "b.mp4", "c.mp4"]
    assert (tmp_path / "c.srt").is_file() and "2 done, 0 skipped, 1 failed" in out and "b.mp4" in out


def test_cli_batch_reports_a_missing_input_and_an_empty_folder(tmp_path, monkeypatch):
    code, called = _batch(tmp_path, monkeypatch, ["a.mp4"], ["a.mp4", "gone.mp4"])
    assert "gone.mp4" in str(code) and called == []      # nothing runs when one name is wrong
    (tmp_path / "empty" / "sub").mkdir(parents=True)
    code, called = _batch(tmp_path, monkeypatch, ["empty/sub/a.mp4"], ["empty"])
    assert "no audio or video files found" in str(code) and "-r" in str(code)


def test_cli_one_file_still_takes_o_as_a_base_path(tmp_path, monkeypatch):
    code, called = _batch(tmp_path, monkeypatch, ["a.mp4"], ["a.mp4", "-f", "srt", "-o", "out/name"])
    assert code == 0 and (tmp_path / "out" / "name.srt").is_file()


def test_batch_runs_setup_once_for_all_files(tmp_path, monkeypatch):
    """Listing the devices loads the model; a folder must pay that once, and nothing may be kept afterwards."""
    from babelscribe import api, backend, models, transcribe
    probes = []
    monkeypatch.setattr(backend, "find_binary", lambda *a, **k: tmp_path / "whisper-cli")
    monkeypatch.setattr(models, "ensure", lambda *a, **k: tmp_path / "m.bin")
    monkeypatch.setattr(backend, "probe_or_refetch", lambda b, m, f=None: (
        probes.append(1) or b, [{"id": 0, "backend": "cpu", "name": "CPU"}]))
    monkeypatch.setattr(transcribe, "run", lambda *a, **k: [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}])
    for n in ("a.wav", "b.wav", "c.wav"):
        (tmp_path / n).write_bytes(b"x")
    done = api.transcribe_many([tmp_path], lang="en", formats=["srt"], log=lambda m: None)
    assert done["succeeded"] == 3 and len(probes) == 1
    api.transcribe_file(tmp_path / "a.wav", lang="en", formats=["srt"], log=lambda m: None)
    assert len(probes) == 2 and api._shared is None

