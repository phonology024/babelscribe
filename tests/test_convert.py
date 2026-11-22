"""`babelscribe convert` (#57): subtitles again from the saved JSON, with no transcription."""
import json
import re
from pathlib import Path

import pytest

from babelscribe import cli, convert, writers

ALL = ["srt", "vtt", "txt", "json", "ass"]


def words(text: str, start: float, per_word: float = 0.5) -> list:
    """Whisper-style tokens: every word carries its leading space, half a second each."""
    return [[tok, round(start + i * per_word, 3), round(start + (i + 1) * per_word, 3)]
            for i, tok in enumerate(re.findall(r"\s*\S+", " " + text))]


def segment(text: str, start: float) -> dict:
    w = words(text, start)
    return {"start": w[0][1], "end": w[-1][2], "text": text, "words": w}


LONG = "And so my fellow Americans ask not what your country can do for you ask what you can do for your country"
SEGS = [segment("Hello there.", 0.0), segment(LONG, 2.0), segment("Thank you.", 20.0)]
META = {"tool": "babelscribe test", "model": "turbo", "lang": "en", "device": "cpu"}


@pytest.fixture
def run(tmp_path):
    """A finished transcription on disk: talk.json and the other four formats next to it."""
    writers.write(json.loads(json.dumps(SEGS)), tmp_path / "talk", ALL, META)
    return tmp_path


def srt_lines(path: Path) -> list[str]:
    return [x for x in path.read_text(encoding="utf-8").splitlines() if x and "-->" not in x and not x.isdigit()]


def test_each_format_from_the_json_equals_what_the_run_wrote(run):
    r = convert.convert_file(run / "talk.json", ALL, out=run / "again" / "talk")
    assert r["segments"] == 3 and r["retimed"] == 0 and len(r["files"]) == 5
    for f in ALL:
        assert (run / "again" / f"talk.{f}").read_text(encoding="utf-8") == (run / f"talk.{f}").read_text(encoding="utf-8"), f


def test_output_lands_next_to_the_json_by_default(run):
    (run / "talk.srt").unlink()
    r = convert.convert_file(run / "talk.json")
    assert r["files"] == [str(run / "talk.srt")] and (run / "talk.srt").is_file()


def test_a_changed_line_width_rewraps(run):
    before = srt_lines(run / "talk.srt")
    convert.convert_file(run / "talk.json", ["srt"], max_line_chars=20)
    after = srt_lines(run / "talk.srt")
    assert max(map(len, before)) > 20 and max(map(len, after)) <= 20
    assert " ".join(after) == " ".join(before), "same words, only wrapped differently"


def test_an_edited_text_shows_up_in_every_format_with_its_timing(run):
    data = json.loads((run / "talk.json").read_text(encoding="utf-8"))
    data["segments"][1]["text"] = LONG.replace("Americans", "Thai friends")       # long cue: wrapped from the words
    data["segments"][2]["text"] = "Thanks a lot."                                 # short cue: written from the text
    (run / "talk.json").write_text(json.dumps(data), encoding="utf-8")
    r = convert.convert_file(run / "talk.json", ["srt", "vtt", "txt", "ass"])
    assert r["retimed"] == 2
    for f in ("srt", "vtt", "txt", "ass"):
        text = (run / f"talk.{f}").read_text(encoding="utf-8")
        flat = re.sub(r"\s+", " ", re.sub(r"\{\\k\d+\}", "", text).replace("\\N", " "))
        assert "fellow Thai friends ask not" in flat and "Americans" not in flat, f
        assert "Thanks a lot." in flat and "Thank you." not in flat, f
    # the cue that holds the edit still starts where the segment did, and times never run backwards
    stamps = re.findall(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)", (run / "talk.srt").read_text(encoding="utf-8"))
    secs = [(int(a) * 3600 + int(b) * 60 + int(c) + int(d) / 1000, int(e) * 3600 + int(f) * 60 + int(g) + int(h) / 1000)
            for a, b, c, d, e, f, g, h in stamps]
    assert secs[1][0] == 2.0 and all(a < b for a, b in secs) and all(x[1] <= y[0] for x, y in zip(secs, secs[1:]))


def test_retime_keeps_unchanged_words_and_shares_time_among_new_ones():
    seg = segment("my fellow Americans ask not", 0.0)        # five words, 0.5 s each
    seg["text"] = "my fellow Thai friends ask not"
    assert convert.retime_words(seg)
    got = {w[0].strip(): (w[1], w[2]) for w in seg["words"]}
    assert got["my"] == (0.0, 0.5) and got["fellow"] == (0.5, 1.0) and got["ask"] == (1.5, 2.0) and got["not"] == (2.0, 2.5)
    assert got["Thai"][0] >= 1.0 and got["friends"][1] <= 1.5 and got["Thai"][1] <= got["friends"][0] + 1e-9
    assert "".join(w[0] for w in seg["words"]).strip() == seg["text"]


def test_retime_leaves_untouched_and_untimed_segments_alone():
    seg = segment("Hello there.", 0.0)
    before = json.dumps(seg)
    assert not convert.retime_words(seg) and json.dumps(seg) == before
    bare = {"start": 0.0, "end": 1.0, "text": "edited by hand", "words": []}
    assert not convert.retime_words(bare)


def test_retime_text_without_spaces():
    seg = {"start": 0.0, "end": 3.0, "text": "สวัสดีครับผม", "words": [["สวัสดี", 0.0, 1.0], ["ครับ", 1.0, 2.0], ["ผม", 2.0, 3.0]]}
    seg["text"] = "สวัสดีค่ะผม"
    assert convert.retime_words(seg)
    assert [w[0] for w in seg["words"]] == ["สวัสดี", "ค่ะ", "ผม"]
    assert seg["words"][0][1:] == [0.0, 1.0] and seg["words"][2][1:] == [2.0, 3.0]
    assert 1.0 <= seg["words"][1][1] < seg["words"][1][2] <= 2.0


def cues(**rules) -> list[dict]:
    return writers._reading_rules(writers._subtitle_cues(json.loads(json.dumps(SEGS)), 42, rules.pop("max_lines", 2)), **rules)


def test_max_lines_one_gives_single_line_cues():
    assert any("\n" in c["text"] for c in cues())
    assert not any("\n" in c["text"] for c in cues(max_lines=1))


def test_max_duration_cuts_long_cues_at_word_boundaries():
    assert max(c["end"] - c["start"] for c in cues()) > 3
    cut = cues(max_duration=3)
    assert max(c["end"] - c["start"] for c in cut) <= 3 + 1e-9
    assert " ".join(c["text"].replace("\n", " ") for c in cut) == " ".join(s["text"] for s in SEGS)
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(cut, cut[1:]))


def test_min_duration_extends_but_never_into_the_next_cue():
    short = [{"start": 0.0, "end": 0.3, "text": "Hi.", "lines": []}, {"start": 0.8, "end": 1.0, "text": "Yes.", "lines": []}]
    out = writers._reading_rules(short, min_duration=1.0)
    assert out[0]["end"] == 0.8, "stops where the next cue starts"
    assert out[1]["end"] == 1.8, "the last cue has room"
    assert short[0]["end"] == 0.3, "the input cues are not changed in place"


def test_max_cps_keeps_a_fast_cue_up_longer():
    fast = [{"start": 0.0, "end": 1.0, "text": "x" * 34, "lines": []}, {"start": 5.0, "end": 6.0, "text": "ok", "lines": []}]
    out = writers._reading_rules(fast, max_cps=17)
    assert out[0]["end"] == 2.0 and out[1]["end"] == 6.0       # 34 characters at 17 per second = 2 s


def test_rules_reject_nonsense():
    for bad in ({"max_cps": 0}, {"min_duration": -1}, {"max_duration": 0}):
        with pytest.raises(ValueError):
            writers._reading_rules([], **bad)
    with pytest.raises(ValueError):
        writers._subtitle_cues(SEGS, 42, 0)


def test_cli_convert(run, capsys):
    cli.main(["convert", str(run / "talk.json"), "-f", "srt,vtt", "--max-line-chars", "20", "-o", str(run / "out" / "x")])
    assert "3 segments" in capsys.readouterr().out
    assert (run / "out" / "x.srt").is_file() and (run / "out" / "x.vtt").is_file()
    assert max(map(len, srt_lines(run / "out" / "x.srt"))) <= 20


def test_cli_convert_explains_bad_input(run, tmp_path):
    (tmp_path / "broken.json").write_text('{"segments": [', encoding="utf-8")
    (tmp_path / "other.json").write_text('{"hello": 1}', encoding="utf-8")
    for path, hint in ((tmp_path / "missing.json", "no such file"), (tmp_path / "broken.json", "not valid JSON"),
                       (tmp_path / "other.json", "not a babelscribe JSON")):
        with pytest.raises(SystemExit) as e:
            cli.main(["convert", str(path)])
        assert hint in str(e.value)
    with pytest.raises(SystemExit) as e:
        cli.main(["convert", str(run / "talk.json"), str(run / "talk.json"), "-o", "x"])
    assert "one JSON at a time" in str(e.value)


def test_mcp_convert_subtitles_and_json_in_the_default_formats(run):
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import mcp_server
    srv = mcp_server.build()
    tools = {t.name: t for t in anyio.run(srv.list_tools)}
    assert "convert_subtitles" in tools
    for name in ("transcribe", "transcribe_folder"):
        schema = getattr(tools[name], "input_schema", None) or tools[name].inputSchema
        assert "json" in schema["properties"]["formats"]["default"], f"{name}: convert needs the json to exist"
    anyio.run(lambda: srv.call_tool("convert_subtitles", {
        "json_path": str(run / "talk.json"), "formats": "vtt", "max_line_chars": 20, "output_dir": str(run / "mcp")}))
    vtt = (run / "mcp" / "talk.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT") and max(len(x) for x in vtt.splitlines() if "-->" not in x) <= 20
    with pytest.raises(Exception) as e:
        anyio.run(lambda: srv.call_tool("convert_subtitles", {"json_path": str(run / "nope.json")}))
    assert "no such file" in str(e.value)


def test_mcp_tells_the_client_what_went_wrong(tmp_path):
    """An AI app only sees the text of the error. "Error executing tool transcribe" tells the user nothing."""
    pytest.importorskip("mcp.server.mcpserver")
    import anyio
    from babelscribe import mcp_server
    srv = mcp_server.build()
    with pytest.raises(Exception) as e:
        anyio.run(lambda: srv.call_tool("transcribe", {"file_path": str(tmp_path / "missing.mp4")}))
    assert "no such file" in str(e.value) and "missing.mp4" in str(e.value)

