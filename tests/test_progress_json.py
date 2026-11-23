"""--progress-json: the machine-readable progress the desktop app reads from babelscribe.exe (#18)."""
import json
import sys

import pytest

from babelscribe import api, cli


def _events(text: str) -> list[dict]:
    lines = [line for line in text.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]      # every stdout line must be one JSON object


def test_one_file_reports_log_progress_and_the_result_as_json_lines(monkeypatch, capsys, tmp_path):
    seen = {}

    def fake(src, log=print, progress=None, **k):
        seen.update(k)
        print("downloading model turbo ...")         # a stray print, as models.ensure does: must not reach stdout
        log("language: en")
        for pct in (0, 12.34, 12.34, 50, 40, 100):    # repeats and a step back are not reported
            progress(pct)
        return {"files": [str(tmp_path / "talk.srt")], "lang": "en", "segments": 3, "seconds": 1.5, "text": "hi",
                "model": "turbo", "device": "cpu CPU", "tool": "babelscribe test"}
    monkeypatch.setattr(api, "transcribe_file", fake)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True, raising=False)   # even in a terminal: no bar
    cli.main(["talk.mp4", "-f", "srt", "--progress-json"])
    out = capsys.readouterr()
    ev = _events(out.out)
    assert [e["percent"] for e in ev if e["event"] == "progress"] == [0.0, 12.3, 50.0, 100.0]
    assert all(e["stage"] == "transcribe" for e in ev if e["event"] == "progress")
    assert {"event": "log", "message": "language: en"} in ev
    assert ev[-1]["event"] == "done" and ev[-1]["files"] == [str(tmp_path / "talk.srt")] and ev[-1]["segments"] == 3
    assert "downloading model" in out.err and "downloading model" not in out.out
    assert "[" not in out.err.replace("downloading", ""), "no progress bar is drawn"
    assert seen["formats"] == ["srt"]
    assert sys.stdout is not sys.stderr, "stdout is put back afterwards"


def test_an_error_is_one_error_event_and_exit_code_1(monkeypatch, capsys):
    def missing(src, **k):
        raise FileNotFoundError("no such file: talk.mp4")
    monkeypatch.setattr(api, "transcribe_file", missing)
    with pytest.raises(SystemExit) as e:
        cli.main(["talk.mp4", "--progress-json"])
    assert e.value.code == 1
    ev = _events(capsys.readouterr().out)
    assert ev == [{"event": "error", "message": "no such file: talk.mp4"}]


def test_an_unexpected_exception_is_reported_too(monkeypatch, capsys):
    def broken(src, **k):
        raise KeyError("segments")
    monkeypatch.setattr(api, "transcribe_file", broken)
    with pytest.raises(SystemExit) as e:
        cli.main(["talk.mp4", "--progress-json"])
    assert e.value.code == 1
    out = capsys.readouterr()
    ev = _events(out.out)
    assert ev[-1]["event"] == "error" and "KeyError" in ev[-1]["message"]
    assert "Traceback" in out.err


def test_non_ascii_text_stays_ascii_on_the_wire(monkeypatch, capsys):
    """A piped stdout on Windows is in the ANSI code page; escaped JSON survives any of them."""
    monkeypatch.setattr(api, "transcribe_file", lambda src, **k: {"files": ["C:/คลิป/งาน.srt"], "text": "สวัสดี"})
    cli.main(["งาน.mp4", "--progress-json"])
    raw = capsys.readouterr().out
    assert raw.isascii()
    assert _events(raw)[-1]["text"] == "สวัสดี"


def test_a_folder_ends_with_the_batch_summary(monkeypatch, capsys, tmp_path):
    for n in ("a.wav", "b.wav"):
        (tmp_path / n).write_bytes(b"x")

    def fake(src, log=print, progress=None, **k):
        progress(100)
        return {"files": [str(src) + ".srt"], "lang": "en", "segments": 1, "seconds": 0.1, "text": ""}
    monkeypatch.setattr(api, "transcribe_file", fake)
    cli.main([str(tmp_path), "--progress-json"])
    ev = _events(capsys.readouterr().out)
    assert any(e["event"] == "log" and "[1/2] a.wav" in e["message"] for e in ev)
    assert ev[-1]["event"] == "done" and ev[-1]["total"] == 2 and ev[-1]["succeeded"] == 2


def test_without_the_flag_nothing_changes(monkeypatch, capsys):
    got = {}
    monkeypatch.setattr(api, "transcribe_file", lambda *a, **k: got.update(k))
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False, raising=False)
    cli.main(["talk.mp4"])
    assert "log" not in got and "progress" not in got
    assert capsys.readouterr().out == ""
